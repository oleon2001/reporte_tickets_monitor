"""
Consultas GLPI (MySQL) para el reporte de tickets.

Tres reportes MUTUAMENTE EXCLUYENTES (un ticket aparece en un solo bloque,
priorizando severidad Vencidos > Por vencer > Al 70%):

  * Query 1 -> tickets al 70% del tiempo, vigentes y con MÁS que
               NEAR_DUE_HOURS por vencer (no se solapa con la Query 2).
  * Query 2 -> tickets PRÓXIMOS a vencer (no vencidos, <= NEAR_DUE_HOURS horas).
  * Query 3 -> tickets YA VENCIDOS.

Además del SQL, aquí vive el formateo de los mensajes de Telegram:
  * build_group_summary           -> resumen consolidado para el grupo.
  * build_technician_messages     -> un mensaje por técnico con sus casos.
  * technician_totals             -> carga por técnico (para la gráfica PNG).

La conexión se abre y cierra por consulta (con cierre seguro de cursor/conexión).
"""
import datetime
import logging

import mysql.connector

import config

log = logging.getLogger(__name__)


# =========================================================================
# TIPOS DE REPORTE (identificadores internos)
# =========================================================================
KIND_VENCIDOS = "vencidos"
KIND_POR_VENCER = "por_vencer"
KIND_70 = "setenta"

_EMOJI = {
    KIND_VENCIDOS: "🔴",
    KIND_POR_VENCER: "🟠",
    KIND_70: "🟡",
}


# =========================================================================
# QUERIES
# =========================================================================
# Al 70%: >= 70% del tiempo consumido, sigue vigente y le resta MÁS que la
# ventana de "próximos a vencer" (así no se solapa con la Query 2).
QUERY_1_TICKETS_70_PORCIENTO = f"""
SELECT
    gt.id AS ticket_id,
    gt.name AS titulo_ticket,
    gt.date AS fecha_creacion,
    gt.time_to_resolve AS fecha_vencimiento,
    gt.priority AS priority,
    gu.id AS tecnico_id,
    gu.name AS tecnico_login,
    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
    TIMESTAMPDIFF(SECOND, gt.date, gt.time_to_resolve) AS tiempo_total_segundos,
    TIMESTAMPDIFF(SECOND, gt.date, NOW()) AS tiempo_transcurrido_segundos,
    ROUND((TIMESTAMPDIFF(SECOND, gt.date, NOW()) * 100.0 /
           NULLIF(TIMESTAMPDIFF(SECOND, gt.date, gt.time_to_resolve), 0)), 2) AS porcentaje_transcurrido
FROM glpi_tickets gt
INNER JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
INNER JOIN glpi_users gu ON gtu.users_id = gu.id
INNER JOIN glpi_groups_users ggu ON gu.id = ggu.users_id
WHERE gt.is_deleted = 0
    AND gt.status NOT IN (6)
    AND gt.time_to_resolve IS NOT NULL
    AND ggu.groups_id = {int(config.GLPI_GROUP_ID)}
    AND gt.solvedate IS NULL
    AND TIMESTAMPDIFF(SECOND, gt.date, NOW()) >= (TIMESTAMPDIFF(SECOND, gt.date, gt.time_to_resolve) * 0.7)
    AND TIMESTAMPDIFF(SECOND, gt.date, NOW()) < TIMESTAMPDIFF(SECOND, gt.date, gt.time_to_resolve)
    AND gt.time_to_resolve > DATE_ADD(NOW(), INTERVAL {int(config.NEAR_DUE_HOURS)} HOUR)
ORDER BY gt.time_to_resolve ASC;
"""

# Próximos a vencer: aún NO vencidos y faltan <= NEAR_DUE_HOURS horas.
QUERY_2_TICKETS_POR_VENCER = f"""
SELECT
    gt.id AS ticket_id,
    gt.name AS titulo_ticket,
    gt.date AS fecha_creacion,
    gt.time_to_resolve AS fecha_vencimiento,
    gt.priority AS priority,
    gu.id AS tecnico_id,
    gu.name AS tecnico_login,
    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
    TIMESTAMPDIFF(MINUTE, NOW(), gt.time_to_resolve) AS minutos_restantes,
    'POR_VENCER' AS estado_vencimiento
FROM glpi_tickets gt
INNER JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
INNER JOIN glpi_users gu ON gtu.users_id = gu.id
INNER JOIN glpi_groups_users ggu ON gu.id = ggu.users_id
WHERE gt.is_deleted = 0
    AND gt.status NOT IN (6)
    AND gt.time_to_resolve IS NOT NULL
    AND ggu.groups_id = {int(config.GLPI_GROUP_ID)}
    AND gt.solvedate IS NULL
    AND gt.time_to_resolve >= NOW()
    AND gt.time_to_resolve <= DATE_ADD(NOW(), INTERVAL {int(config.NEAR_DUE_HOURS)} HOUR)
ORDER BY gt.time_to_resolve ASC;
"""

# Vencidos: ya pasó el time_to_resolve.
QUERY_3_TICKETS_VENCIDOS = f"""
SELECT
    gt.id AS ticket_id,
    gt.name AS titulo_ticket,
    gt.date AS fecha_creacion,
    gt.time_to_resolve AS fecha_vencimiento,
    gt.priority AS priority,
    gu.id AS tecnico_id,
    gu.name AS tecnico_login,
    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
    TIMESTAMPDIFF(MINUTE, gt.time_to_resolve, NOW()) AS minutos_vencido,
    'VENCIDO' AS estado_vencimiento
FROM glpi_tickets gt
INNER JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
INNER JOIN glpi_users gu ON gtu.users_id = gu.id
INNER JOIN glpi_groups_users ggu ON gu.id = ggu.users_id
WHERE gt.is_deleted = 0
    AND gt.status NOT IN (6)
    AND gt.time_to_resolve IS NOT NULL
    AND ggu.groups_id = {int(config.GLPI_GROUP_ID)}
    AND gt.solvedate IS NULL
    AND gt.time_to_resolve < NOW()
ORDER BY gt.time_to_resolve ASC;
"""

# Orden de severidad para reportes y mensajes (más urgente primero).
GLPI_JOBS = [
    {
        "name": "Query 3 - Tickets vencidos",
        "kind": KIND_VENCIDOS,
        "label": "🔴 Vencidos",
        "query": QUERY_3_TICKETS_VENCIDOS,
    },
    {
        "name": f"Query 2 - Tickets próximos a vencer (<={int(config.NEAR_DUE_HOURS)}h)",
        "kind": KIND_POR_VENCER,
        "label": f"🟠 Próximos a vencer (≤{int(config.NEAR_DUE_HOURS)}h)",
        "query": QUERY_2_TICKETS_POR_VENCER,
    },
    {
        "name": "Query 1 - Tickets al 70%",
        "kind": KIND_70,
        "label": "🟡 Al 70% del tiempo",
        "query": QUERY_1_TICKETS_70_PORCIENTO,
    },
]


# =========================================================================
# EJECUCIÓN
# =========================================================================
def execute_query(query, query_name) -> list:
    """Ejecuta una consulta en la BD GLPI y devuelve las filas (dict)."""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**config.GLPI_DB)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        rows = cursor.fetchall()
        return rows
    except Exception as exc:  # noqa: BLE001
        log.error("Error ejecutando %s: %s", query_name, exc)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================================================================
# HELPERS DE FORMATO
# =========================================================================
_PRIORITY = {1: "Muy baja", 2: "Baja", 3: "Media", 4: "Alta", 5: "Muy alta", 6: "Mayor"}


def _esc(text):
    """Escapa texto del usuario para Telegram (parse_mode=HTML)."""
    out = str(text if text is not None else "")
    return out.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(text, limit=90):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_duracion(minutos):
    """Convierte minutos a un texto legible: '45m', '3h 20m', '2d 5h'."""
    try:
        minutos = int(minutos or 0)
    except (TypeError, ValueError):
        return "0m"
    if minutos < 60:
        return f"{minutos}m"
    horas, mins = divmod(minutos, 60)
    if horas < 24:
        return f"{horas}h {mins}m" if mins else f"{horas}h"
    dias, hrs = divmod(horas, 24)
    return f"{dias}d {hrs}h" if hrs else f"{dias}d"


def _progress_bar(porcentaje, width=10):
    """Barra visual: '▰▰▰▰▰▰▱▱▱▱ 62%'."""
    try:
        pct = max(0.0, min(100.0, float(porcentaje or 0)))
    except (TypeError, ValueError):
        pct = 0.0
    llenos = int(round(pct * width / 100.0))
    return "▰" * llenos + "▱" * (width - llenos) + f" {pct:.0f}%"


def _deadline(value):
    """Formatea la fecha de vencimiento como 'dd/mm HH:MM' (o '' si no aplica)."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%d/%m %H:%M")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).strftime("%d/%m %H:%M")
        except ValueError:
            continue
    return text[:16]


def _priority_tag(priority):
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        return ""
    if priority >= 4:
        return f" · 🔺{_PRIORITY.get(priority, '')}"
    return ""


def _ticket_url(ticket_id):
    base = (getattr(config, "GLPI_BASE_URL", "") or "").strip()
    if not base:
        return ""
    return f"{base.rstrip('/')}/front/ticket.form.php?id={ticket_id}"


def _ticket_time_note(row, kind):
    if kind == KIND_VENCIDOS:
        return f"venció hace {_fmt_duracion(row.get('minutos_vencido'))}"
    if kind == KIND_POR_VENCER:
        return f"vence en {_fmt_duracion(row.get('minutos_restantes'))}"
    # KIND_70: barra de avance + tiempo restante calculado en segundos.
    porcentaje = row.get("porcentaje_transcurrido", 0) or 0
    restante_min = (
        (row.get("tiempo_total_segundos", 0) or 0) - (row.get("tiempo_transcurrido_segundos", 0) or 0)
    ) / 60
    return f"{_progress_bar(porcentaje)} · restan {_fmt_duracion(restante_min)}"


def _render_ticket_line(row, kind):
    ticket_id = row.get("ticket_id")
    titulo = _truncate(_esc(row.get("titulo_ticket")), 90)
    line = f"• <b>#{ticket_id}</b> · {titulo}{_priority_tag(row.get('priority'))}"
    note = _ticket_time_note(row, kind)
    if note:
        line += f"\n     ⏱ {note}"
    deadline = _deadline(row.get("fecha_vencimiento"))
    if deadline:
        line += f"\n     ⏰ {deadline}"
    url = _ticket_url(ticket_id)
    if url:
        line += f"\n     🔗 {url}"
    return line


# =========================================================================
# AGRUPACIÓN POR TÉCNICO
# =========================================================================
def _collect_by_technician(results):
    """results: {kind: [rows]} -> {login: {login, nombre, tickets: {kind: [rows]}}}."""
    tech = {}
    for kind, rows in results.items():
        for row in rows:
            login = row.get("tecnico_login") or row.get("tecnico_asignado") or "sin_asignar"
            info = tech.get(login)
            if info is None:
                info = {
                    "login": login,
                    "nombre": row.get("tecnico_asignado") or login,
                    "tickets": {},
                }
                tech[login] = info
            info["tickets"].setdefault(kind, []).append(row)
    return tech


def _lookup_member(members, login, nombre):
    """Busca el chat_id por login de GLPI; fallback por nombre (case-insensitive)."""
    if not members:
        return None
    if login in members:
        return members[login]
    target = (nombre or "").strip().lower()
    for key, value in members.items():
        if str(key).strip().lower() == target:
            return value
    return None


# =========================================================================
# MENSAJES
# =========================================================================
def build_group_summary(results, timestamp=None, unmapped=None):
    """Resumen consolidado para el grupo: totales + desglose por técnico."""
    ts = timestamp or datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    total = sum(len(rows) for rows in results.values())
    lines = ["🎫 <b>REPORTE DE TICKETS GLPI</b>", f"🗓 {ts}"]

    if total == 0:
        lines.append("")
        lines.append("✅ Sin tickets vencidos, próximos a vencer ni al 70%.")
        return "\n".join(lines)

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    for job in GLPI_JOBS:
        n = len(results.get(job["kind"], []))
        share = n * 100.0 / total if total else 0
        lines.append(f"{job['label']}: <b>{n}</b>  {_progress_bar(share)}")
    lines.append(f"Σ <b>Total: {total}</b>")

    tech = _collect_by_technician(results)
    if tech:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("👷 <b>Por técnico</b>")
        ranking = sorted(
            tech.values(),
            key=lambda info: sum(len(v) for v in info["tickets"].values()),
            reverse=True,
        )
        for pos, info in enumerate(ranking, 1):
            counter = info["tickets"]
            total_tec = sum(len(v) for v in counter.values())
            desglose = " ".join(
                f"{_EMOJI[job['kind']]}{len(counter[job['kind']])}"
                for job in GLPI_JOBS
                if counter.get(job["kind"])
            )
            lines.append(f"{pos}. <b>{_esc(info['nombre'])}</b> — {total_tec}  ({desglose})")

    if unmapped:
        lines.append("")
        lines.append("⚠️ Sin chat_id configurado: " + ", ".join(_esc(n) for n in unmapped))

    return "\n".join(lines)


def _render_technician_message(info):
    total = sum(len(rows) for rows in info["tickets"].values())
    lines = [
        f"🔔 Hola <b>{_esc(info['nombre'])}</b>",
        f"Tienes <b>{total}</b> caso(s) asignado(s):",
    ]
    for job in GLPI_JOBS:
        rows = info["tickets"].get(job["kind"]) or []
        if not rows:
            continue
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{job['label']} <b>({len(rows)})</b>")
        lines.extend(_render_ticket_line(row, job["kind"]) for row in rows)
    return "\n".join(lines)


def build_technician_messages(results, members):
    """Devuelve [(login, nombre, chat_id|None, texto)] por cada técnico con casos."""
    messages = []
    for login, info in _collect_by_technician(results).items():
        chat_id = _lookup_member(members, login, info["nombre"])
        messages.append((login, info["nombre"], chat_id, _render_technician_message(info)))
    return messages


def technician_totals(results):
    """[(nombre, total, {kind: n})] ordenado de mayor a menor carga (para gráficas)."""
    out = []
    for info in _collect_by_technician(results).values():
        counter = info["tickets"]
        out.append((
            info["nombre"],
            sum(len(v) for v in counter.values()),
            {job["kind"]: len(counter.get(job["kind"], [])) for job in GLPI_JOBS},
        ))
    return sorted(out, key=lambda item: item[1], reverse=True)


def list_group_users():
    """Usuarios de GLPI del grupo reportado: [{id, login, nombre}]."""
    query = f"""
SELECT DISTINCT gu.id AS id,
       gu.name AS login,
       CONCAT(gu.realname, ' ', gu.firstname) AS nombre
FROM glpi_users gu
INNER JOIN glpi_groups_users ggu ON gu.id = ggu.users_id
WHERE ggu.groups_id = {int(config.GLPI_GROUP_ID)}
ORDER BY nombre;
"""
    return execute_query(query, "Usuarios del grupo GLPI")


# =========================================================================
# MOCK (pruebas locales sin BD)
# =========================================================================
MOCK_ROWS = {
    "Query 3 - Tickets vencidos": [
        {
            "ticket_id": 202,
            "titulo_ticket": "Impresora fiscal no imprime",
            "fecha_creacion": "2026-10-10 09:00:00",
            "fecha_vencimiento": "2026-10-10 12:00:00",
            "priority": 4,
            "tecnico_id": 8,
            "tecnico_login": "mlopez",
            "tecnico_asignado": "Maria Lopez",
            "minutos_vencido": 120,
            "estado_vencimiento": "VENCIDO",
        }
    ],
    "Query 2 - Tickets próximos a vencer (<=24h)": [
        {
            "ticket_id": 210,
            "titulo_ticket": "Caja sin comunicación",
            "fecha_creacion": "2026-10-10 08:00:00",
            "fecha_vencimiento": "2026-10-11 11:20:00",
            "priority": 3,
            "tecnico_id": 5,
            "tecnico_login": "jperez",
            "tecnico_asignado": "Juan Perez",
            "minutos_restantes": 200,
            "estado_vencimiento": "POR_VENCER",
        }
    ],
    "Query 1 - Tickets al 70%": [
        {
            "ticket_id": 101,
            "titulo_ticket": "Lector de código de barras no lee",
            "fecha_creacion": "2026-10-10 08:00:00",
            "fecha_vencimiento": "2026-10-13 08:00:00",
            "priority": 2,
            "tecnico_id": 5,
            "tecnico_login": "jperez",
            "tecnico_asignado": "Juan Perez",
            "tiempo_total_segundos": 259200,
            "tiempo_transcurrido_segundos": 190000,
            "porcentaje_transcurrido": 73.3,
        }
    ],
}


def mock_rows(query_name):
    """Devuelve filas de ejemplo para una consulta (modo mock)."""
    return MOCK_ROWS.get(query_name, [])
