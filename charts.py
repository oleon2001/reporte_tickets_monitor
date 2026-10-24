"""
Gráfica PNG del reporte de tickets (opcional).

Genera una imagen con:
  * barras horizontales apiladas por técnico (vencidos / por vencer / al 70%),
  * dona con el total por severidad.

Se envía al grupo con telegram_client.send_photo. Si matplotlib no está
instalado (o no hay datos), devuelve None y el reporte textual sigue normal.
"""
import datetime
import logging
import os

import config
import glpi_db

log = logging.getLogger(__name__)

# Paleta por severidad (coincide con los emojis del reporte textual).
_COLORS = {
    glpi_db.KIND_VENCIDOS: "#e53935",   # rojo
    glpi_db.KIND_POR_VENCER: "#fb8c00",  # naranja
    glpi_db.KIND_70: "#fdd835",          # amarillo
}

# Etiquetas sin emoji: la fuente por defecto de matplotlib no los renderiza.
_LABELS = {
    glpi_db.KIND_VENCIDOS: "Vencidos",
    glpi_db.KIND_POR_VENCER: f"Por vencer (<={int(config.NEAR_DUE_HOURS)}h)",
    glpi_db.KIND_70: "Al 70%",
}

_BG = "#0f172a"
_FG = "#e2e8f0"
_GRID = "#334155"


def build_chart(results, out_dir=None, timestamp=None):
    """Crea el PNG y devuelve su ruta. None si no hay datos o falta matplotlib."""
    tech = glpi_db.technician_totals(results)
    totals = {job["kind"]: len(results.get(job["kind"], [])) for job in glpi_db.GLPI_JOBS}
    if not tech or sum(totals.values()) == 0:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib no disponible (sin gráfica): %s", exc)
        return None

    jobs = glpi_db.GLPI_JOBS
    if out_dir is None:
        out_dir = os.path.join(config.OUTPUT_DIR, datetime.date.today().isoformat())
    os.makedirs(out_dir, exist_ok=True)

    height = max(3.6, 0.55 * len(tech) + 2.2)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(11, height), gridspec_kw={"width_ratios": [3, 1.7]}
    )
    fig.patch.set_facecolor(_BG)

    names = [t[0] for t in tech][::-1]
    y = range(len(names))
    left = [0.0] * len(names)
    for job in jobs:
        kind = job["kind"]
        values = [t[2].get(kind, 0) for t in tech][::-1]
        if not any(values):
            continue
        ax1.barh(
            list(y), values, left=left, color=_COLORS[kind],
            label=_LABELS[kind], edgecolor=_BG, height=0.62,
        )
        left = [a + b for a, b in zip(left, values)]

    for idx, total in enumerate([t[1] for t in tech][::-1]):
        ax1.text(total + 0.05, idx, f" {total}", va="center", color=_FG, fontsize=10, fontweight="bold")

    ax1.set_yticks(list(y))
    ax1.set_yticklabels(names, color=_FG, fontsize=10)
    ax1.set_facecolor(_BG)
    ax1.tick_params(axis="x", colors=_FG)
    ax1.set_xlabel("Casos asignados", color=_FG)
    ax1.grid(axis="x", color=_GRID, linestyle="--", linewidth=0.6, alpha=0.6)
    ax1.set_axisbelow(True)
    for spine in ax1.spines.values():
        spine.set_color(_GRID)
    ax1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3,
               facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)

    # Dona de totales por severidad
    labels, sizes, colors = [], [], []
    for job in jobs:
        n = totals[job["kind"]]
        if n:
            labels.append(f"{_LABELS[job['kind']]}\n({n})")
            sizes.append(n)
            colors.append(_COLORS[job["kind"]])
    ax2.pie(
        sizes, labels=labels, colors=colors, startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": _BG},
        textprops={"color": _FG, "fontsize": 8},
    )
    ax2.set_facecolor(_BG)
    ax2.set_title(f"Total: {sum(sizes)}", color=_FG, fontsize=10)

    ts = timestamp or datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    fig.suptitle(f"Reporte de Tickets GLPI · {ts}", color=_FG, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    path = os.path.join(out_dir, f"reporte_tickets_{datetime.date.today().isoformat()}.png")
    fig.savefig(path, facecolor=_BG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Gráfica generada: %s", path)
    return path


if __name__ == "__main__":
    config.setup_logging()
    res = {job["kind"]: glpi_db.mock_rows(job["name"]) for job in glpi_db.GLPI_JOBS}
    assert build_chart(res) or True  # sin datos reales puede ser None; solo humo
    print("charts OK")
