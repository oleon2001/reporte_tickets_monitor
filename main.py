"""
Reporte de tickets GLPI (MySQL) + Monitor de Ventas EPA -> Telegram.

Envía siempre un resumen al grupo (con gráfica PNG opcional) y, además, un
mensaje privado a cada técnico con sus propios casos (si su chat_id está
configurado). Después consulta el Monitor de Ventas EPA y envía su sección.

Uso:
    python main.py                    # modo continuo (systemd), cada 6 horas
    python main.py --once             # ejecuta una vez y termina (cron)
    python main.py --mock --dry-run   # sin red: datos simulados, sin envío
    python main.py --inspect          # vuelca HTML/screenshots del Monitor
    python main.py --only SV          # solo el Monitor de un país
    python main.py --no-monitor       # solo los reportes GLPI
    python main.py --no-chart         # sin gráfica PNG del reporte
    python main.py --test-chat 12345  # envía todo a un chat de prueba

Los fallos del Monitor NO bloquean los reportes GLPI: si el Monitor falla, se
ejecutan igual los queries y se envía el error al grupo de Telegram.
"""
import argparse
import datetime
import logging
import os
import sys
import time

import config
import charts
import glpi_db
import monitor
import telegram_client

log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Reporte de tickets GLPI + Monitor de Ventas EPA")
    p.add_argument("--once", action="store_true", help="ejecuta una vez y termina (cron)")
    p.add_argument("--mock", action="store_true", help="datos simulados (sin red)")
    p.add_argument("--dry-run", action="store_true", help="genera todo pero no envía")
    p.add_argument("--no-confirm", action="store_true", help="(compatibilidad) sin confirmación")
    p.add_argument("--no-chart", action="store_true", help="no genera la gráfica PNG")
    p.add_argument("--inspect", action="store_true", help="vuelca HTML/screenshots del Monitor")
    p.add_argument("--only", default="", help="países del Monitor a procesar, ej: SV")
    p.add_argument("--no-monitor", action="store_true", help="omite el Monitor de Ventas")
    p.add_argument("--test-chat", default="",
                   help="envía todo a este chat_id (prueba) en lugar de grupo+privados")
    p.add_argument("--interval", type=int, default=21600,
                   help="segundos entre ciclos en modo continuo (por defecto 6h)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------
def _send(text, dry_run, chat_id=None):
    if not text:
        return
    if dry_run:
        print(text)
        return
    try:
        telegram_client.send_message(text, chat_id=chat_id)
        log.info("Mensaje enviado a Telegram (%d caracteres)", len(text))
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo enviar a Telegram: %s", exc)


def _send_photo(path, caption, dry_run, chat_id=None):
    if not path:
        return
    if dry_run:
        log.info("DRY-RUN: no se envía imagen %s", path)
        return
    try:
        telegram_client.send_photo(path, caption, chat_id=chat_id)
        log.info("Imagen enviada a Telegram: %s", os.path.basename(path))
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo enviar la imagen %s: %s", path, exc)


def _send_to(chat_id, text, dry_run):
    if not text:
        return
    if dry_run:
        print(f"--- DM -> {chat_id} ---\n{text}\n")
        return
    try:
        telegram_client.send_message(text, chat_id=chat_id)
        log.info("DM enviado a %s (%d caracteres)", chat_id, len(text))
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo enviar DM a %s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Reportes GLPI
# ---------------------------------------------------------------------------
def run_glpi(dry_run, mock, chart=True, test_chat=None):
    """Ejecuta las tres consultas GLPI.

    Envía al grupo un resumen consolidado (con gráfica opcional) y, además, un
    mensaje privado a cada técnico con sus propios casos. Si una consulta falla,
    se avisa y se continúa con las demás (los reportes GLPI nunca se detienen por
    un error puntual).
    """
    errors = []
    results = {}

    for job in glpi_db.GLPI_JOBS:
        name = job["name"]
        try:
            rows = glpi_db.mock_rows(name) if mock else glpi_db.execute_query(job["query"], name)
            results[job["kind"]] = rows
            log.info("[%s] %d tickets", name, len(rows))
        except Exception as exc:  # noqa: BLE001
            errors.append(name)
            results[job["kind"]] = []
            log.error("[%s] falló: %s", name, exc)
            _send(f"⚠️ Error en el reporte <b>{name}</b>: {exc}", dry_run, chat_id=test_chat)

    # Mensajes por técnico (necesarios para saber quién no tiene chat_id).
    technician_messages = glpi_db.build_technician_messages(
        results, config.TELEGRAM_MEMBERS
    )
    unmapped = [nombre for _, nombre, chat_id, _ in technician_messages if not chat_id]
    for login, nombre, chat_id, _ in technician_messages:
        if not chat_id:
            log.warning("Técnico sin chat_id configurado: %s (%s)", nombre, login)

    # 1) Gráfica PNG (opcional) al grupo / chat de prueba.
    if chart and config.SEND_CHART:
        try:
            path = charts.build_chart(results)
            if path:
                _send_photo(path, "📊 Reporte de tickets GLPI", dry_run, chat_id=test_chat)
        except Exception as exc:  # noqa: BLE001
            log.error("No se pudo generar/enviar la gráfica: %s", exc)

    # 2) Resumen consolidado para el grupo.
    summary = glpi_db.build_group_summary(results, unmapped=unmapped)
    _send(summary, dry_run, chat_id=test_chat)

    # 3) Mensaje privado a cada técnico con sus casos.
    for _, _, chat_id, text in technician_messages:
        target = test_chat or chat_id
        if not target:
            continue
        _send_to(target, text, dry_run)
        if not dry_run:
            time.sleep(1)

    return errors


# ---------------------------------------------------------------------------
# Monitor de Ventas
# ---------------------------------------------------------------------------
def run_monitor(only, dry_run, mock, inspect, out_dir):
    """Consulta el Monitor de Ventas y envía su sección + errores si los hay."""
    try:
        results = monitor.extract_all(only=only, mock=mock, inspect=inspect, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        # Fallo catastrófico (p. ej. Playwright no instalado): avisar al grupo.
        log.error("Monitor no disponible: %s", exc)
        _send("⚠️ <b>Error en el Monitor de Ventas</b>\n"
              f"{str(exc)[:200]}\n"
              "Los reportes de tickets GLPI se enviaron normalmente.", dry_run)
        return {}

    message = monitor.format_monitor_message(results)
    if message:
        log.info("Monitor de Ventas OK en: %s",
                 ", ".join(r.country for r in results.values() if r.ok))
        _send(message, dry_run)
        if config.MONITOR_SEND_IMAGE and not mock:
            for result in results.values():
                if result.ok and result.screenshot and os.path.exists(result.screenshot):
                    caption = f"Monitor de Ventas — {config.COUNTRIES[result.country]['name']}"
                    _send_photo(result.screenshot, caption, dry_run)

    errors_message = monitor.format_monitor_errors(results)
    if errors_message:
        log.error("Monitor con errores:\n%s", errors_message)
        _send(errors_message, dry_run)

    return results


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
def run_reports(args):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.info("Iniciando ejecución de reportes (%s)...", timestamp)

    # Carpeta de salida (gráfica/screenshots): salidas/DD-MM-YYYY
    date_str = datetime.date.today().strftime("%d-%m-%Y")
    out_dir = os.path.join(config.OUTPUT_DIR, date_str)

    # 1) Reportes GLPI (siempre, independientemente del Monitor).
    glpi_errors = run_glpi(
        args.dry_run, args.mock,
        chart=not args.no_chart,
        test_chat=args.test_chat.strip() or None,
    )

    # 2) Monitor de Ventas (no bloqueante).
    monitor_results = {}
    if not args.no_monitor:
        only = [c.strip().upper() for c in args.only.split(",") if c.strip()] or None
        monitor_results = run_monitor(only, args.dry_run, args.mock, args.inspect, out_dir)

    # Resumen en log
    monitor_errors = [c for c, r in monitor_results.items() if not r.ok]
    log.info("Ciclo completado. GLPI con error: %s | Monitor con error: %s",
             glpi_errors or "ninguno", monitor_errors or "ninguno")
    return glpi_errors, monitor_errors


def main_loop(args):
    log.info("Iniciando sistema de reportes en modo continuo (cada %d s)...", args.interval)
    while True:
        try:
            run_reports(args)
        except Exception as exc:  # noqa: BLE001
            log.error("Error en el ciclo: %s", exc)
        log.info("Esperando %d s hasta la próxima ejecución...", args.interval)
        time.sleep(args.interval)


def main():
    args = parse_args()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except ValueError:
                pass
    config.setup_logging()
    log.info("Reporte de tickets GLPI + Monitor de Ventas EPA")
    if args.mock:
        log.info("MODO MOCK: datos simulados, sin red.")
    if args.dry_run:
        log.info("MODO DRY-RUN: no se envía nada a Telegram.")

    if args.once:
        run_reports(args)
        return 0
    main_loop(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
