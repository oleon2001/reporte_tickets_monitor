"""
Pruebas locales (sin framework): lógica + pipeline mock.

    python test_local.py

No requiere red ni navegador; el modo mock no usa la BD.
"""
import os
import subprocess
import sys

import config
import charts
import glpi_db
import monitor
import telegram_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def test_logic():
    # Datos mock: un caso por reporte, sin solapamiento.
    results = {
        job["kind"]: glpi_db.mock_rows(job["name"]) for job in glpi_db.GLPI_JOBS
    }
    assert len(results[glpi_db.KIND_VENCIDOS]) == 1
    assert len(results[glpi_db.KIND_POR_VENCER]) == 1
    assert len(results[glpi_db.KIND_70]) == 1

    # Las queries de vencidos y próximos NO son la misma consulta.
    q_ven = glpi_db.QUERY_3_TICKETS_VENCIDOS
    q_prox = glpi_db.QUERY_2_TICKETS_POR_VENCER
    q_70 = glpi_db.QUERY_1_TICKETS_70_PORCIENTO
    assert q_ven != q_prox
    assert "time_to_resolve < NOW()" in q_ven
    assert "time_to_resolve >= NOW()" in q_prox
    # La query al 70% excluye la ventana de "por vencer" (sin solape).
    assert "time_to_resolve > DATE_ADD(NOW()" in q_70

    # Resumen de grupo (con barras de lectura, formato HTML).
    summary = glpi_db.build_group_summary(results, timestamp="11/10/2026 08:00")
    assert "REPORTE DE TICKETS GLPI" in summary
    assert "Vencidos: <b>1</b>" in summary
    assert "Próximos a vencer" in summary
    assert "Por técnico" in summary
    assert "▰" in summary

    # Mensajes por técnico: con y sin chat_id.
    members = {"jperez": "555", "Maria Lopez": "777"}
    messages = glpi_db.build_technician_messages(results, members)
    by_login = {login: (chat_id, text) for login, _nombre, chat_id, text in messages}
    assert by_login["jperez"][0] == "555"
    assert by_login["mlopez"][0] == "777"  # mapeado por nombre
    assert "Vencidos" in by_login["mlopez"][1]
    assert "Hola <b>Juan Perez</b>" in by_login["jperez"][1]
    assert "▰" in by_login["jperez"][1]  # barra de avance en el caso al 70%

    # Gráfica PNG (si matplotlib está instalado; si no, devuelve None).
    chart_path = charts.build_chart(results, out_dir=os.path.join(BASE_DIR, "salidas", "test"))
    assert chart_path is None or os.path.exists(chart_path)

    # División de mensajes largos (límite Telegram).
    chunks = telegram_client.split_message("x\n" * 3000, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert len(chunks) > 1

    # Monitor: parseo de la respuesta de la API del Monitor.
    parsed = monitor.parse_ventas_counts(
        {"results": [[{"store": "3", "count": 2307}, {"store": "2", "count": "1.516"}]]}
    )
    assert parsed == [{"tienda": "2", "ventas": 1516}, {"tienda": "3", "ventas": 2307}], parsed

    # SV debe refrescar 2 veces (el Monitor no renderiza bien a la primera).
    assert config.COUNTRIES["SV"]["refresh_count"] == 2
    assert config.COUNTRIES["VE"]["refresh_count"] == 1

    print("[OK] Lógica (resumen de grupo, mensajes por técnico, split, gráfica, Monitor)")


def test_mock_pipeline():
    # Monitor en modo mock (sin red ni navegador).
    res = monitor.extract_all(mock=True)
    assert set(res) == {"VE", "SV", "GT"}
    assert all(r.ok for r in res.values())
    assert "Monitor de Ventas EPA" in monitor.format_monitor_message(res)

    bad = monitor.MonitorResult("SV")
    bad.ok = False
    bad.error = "timeout"
    err = monitor.format_monitor_errors({"SV": bad})
    assert "Error en el Monitor" in err and "SV" in err

    # CLI end-to-end sin red ni envío (GLPI + gráfica + Monitor).
    proc = subprocess.run(
        [sys.executable, "main.py", "--once", "--mock", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=BASE_DIR,
    )
    assert proc.returncode == 0, proc.stderr
    assert "REPORTE DE TICKETS GLPI" in proc.stdout, proc.stdout[-800:]
    assert "Monitor de Ventas EPA" in proc.stdout, proc.stdout[-800:]
    print("[OK] Pipeline mock end-to-end (GLPI + Monitor, sin envío)")


def test_connectivity():
    """Conectividad real de solo lectura (avisos no bloqueantes)."""
    print("\n--- Conectividad (solo lectura) ---")
    fails = []
    try:
        rows = glpi_db.execute_query(
            "SELECT COUNT(*) AS n FROM glpi_tickets LIMIT 1", "conectividad GLPI"
        )
        print(f"  [OK] GLPI MySQL ({rows[0]['n']} tickets)")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] GLPI MySQL: {str(exc)[:70]}")
        fails.append("GLPI")
    return fails


if __name__ == "__main__":
    test_logic()
    test_mock_pipeline()
    fails = test_connectivity()
    print("\n" + "=" * 50)
    if fails:
        print(f"RESULTADO: fallos de conectividad en {len(fails)}: {', '.join(fails)}")
        sys.exit(1)
    print("RESULTADO: lógica y pipeline OK. Conectividad OK.")
