"""
Extracción del Monitor de Ventas EPA (VE / SV / GT).

Fuente de datos: la API REST del Monitor (igual que reporte_joseph), robusta y
sin scraping de la UI. La UI (Playwright) se usa SOLO para el screenshot y, en
SV, se refresca DOS veces porque el Monitor no renderiza bien a la primera
(config COUNTRIES[...]["refresh_count"]).

El módulo NO importa Playwright a nivel de módulo: así `--mock` y los tests
funcionan sin el navegador instalado.
"""
import datetime
import logging
import os
import re

import requests

import config

log = logging.getLogger(__name__)


class MonitorResult:
    def __init__(self, country):
        self.country = country
        self.ok = False
        self.error = ""
        self.ventas_total = 0
        self.stores = []        # [{"tienda": "2", "ventas": 1516}, ...]
        self.screenshot = None
        self.refreshes = 0

    def __repr__(self):
        return (f"<{self.country} ok={self.ok} ventas={self.ventas_total} "
                f"stores={len(self.stores)} err={bool(self.error)}>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_int(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0


def _sort_key(tienda):
    """Ordena tiendas numéricas primero y de forma natural."""
    return (0, int(tienda)) if str(tienda).isdigit() else (1, str(tienda))


# ---------------------------------------------------------------------------
# Datos: API REST del Monitor
# ---------------------------------------------------------------------------
def _flatten_results(items):
    """El API anida las filas en listas; las aplana a una sola lista."""
    flat = []
    for item in items or []:
        flat += item if isinstance(item, list) else [item]
    return flat


def parse_ventas_counts(payload):
    """Extrae [{'tienda','ventas'}] de la respuesta de la API del Monitor."""
    rows = []
    for item in _flatten_results((payload or {}).get("results")):
        store = item.get("store")
        if store is None:
            continue
        rows.append({"tienda": str(store), "ventas": _to_int(item.get("count"))})

    seen, unique = set(), []
    for row in rows:
        if row["tienda"] not in seen:
            seen.add(row["tienda"])
            unique.append(row)
    return sorted(unique, key=lambda r: _sort_key(r["tienda"]))


def _api_login(session):
    """Autentica en el Monitor y devuelve el token crudo (sin 'Bearer')."""
    response = session.post(
        f"{config.MONITOR_API_URL}/v1/auth/login",
        json={"username": config.MONITOR_API_USER, "password": config.MONITOR_API_PASS},
        timeout=config.MONITOR_API_TIMEOUT,
    )
    response.raise_for_status()
    token = response.json().get("token")
    if not token:
        raise RuntimeError("el login del Monitor no devolvió token")
    return token


def api_session():
    """Sesión autenticada reutilizable para el Monitor."""
    session = requests.Session()
    session.headers.update({"Authorization": _api_login(session)})
    return session


def fetch_ventas(country, from_date, to_date, session):
    """VENTAS por tienda del país vía API REST. Fechas en ISO (YYYY-MM-DD).

    Devuelve [{'tienda','ventas'}] ordenado por tienda.
    """
    cc = country.lower()
    response = session.get(
        f"{config.MONITOR_API_URL}/v1/transactions/{config.MONITOR_VENTAS_ENDPOINT}/{cc}",
        params={
            "startDate": from_date,
            "endDate": to_date,
            "page": 1,
            "limit": config.MONITOR_API_LIMIT,
        },
        timeout=config.MONITOR_API_TIMEOUT,
    )
    response.raise_for_status()
    return parse_ventas_counts(response.json())


# ---------------------------------------------------------------------------
# Screenshot: UI del Monitor (best-effort, no bloqueante)
# ---------------------------------------------------------------------------
def _dump_inspect(page, country, out_dir):
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"inspect_monitor_{country}.html"),
                  "w", encoding="utf-8") as fh:
            fh.write(page.content())
        page.screenshot(path=os.path.join(out_dir, f"inspect_monitor_{country}.png"),
                        full_page=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo volcar inspect %s: %s", country, exc)


def _wait_render(page, timeout_ms):
    """Espera a que las tarjetas del Monitor rendericen (best-effort)."""
    try:
        page.wait_for_function(
            "() => /VENTAS/.test(document.body.innerText) && "
            "/Tienda/.test(document.body.innerText)",
            timeout=timeout_ms,
        )
    except Exception:  # noqa: BLE001
        page.wait_for_timeout(8000)


def _capture_ui(page, country, result, out_dir, inspect):
    """Abre la UI del Monitor, refresca (SV 2 veces) y captura el screenshot."""
    meta = config.COUNTRIES[country]
    sel = config.MONITOR_SELECTORS
    url = config.MONITOR_BASE_URL + meta["monitor_path"]

    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=config.MONITOR_DAYS_BACK)).strftime(
        config.MONITOR_DATE_FORMAT
    )
    date_to = today.strftime(config.MONITOR_DATE_FORMAT)

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)

    dates = page.locator(sel["date_from"])
    if dates.count() >= 2:
        dates.nth(0).fill(date_from)
        dates.nth(1).fill(date_to)

    refresh_count = meta.get("refresh_count", 1)
    for attempt in range(1, refresh_count + 1):
        if page.locator(sel["refresh"]).count():
            page.locator(sel["refresh"]).first.click()
        else:
            page.reload(wait_until="domcontentloaded")
        _wait_render(page, config.MONITOR_RENDER_TIMEOUT_MS)
        result.refreshes = attempt
        log.info("[%s] Monitor refresh %d/%d", country, attempt, refresh_count)

    if inspect:
        _dump_inspect(page, country, out_dir)

    if config.MONITOR_SEND_IMAGE and out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"Monitor de Ventas {meta['name']}.png")
        page.screenshot(path=path, full_page=True)
        result.screenshot = path


def _capture_all_ui(results, out_dir, inspect):
    """Captura la UI de cada país. Los fallos NO invalidan los datos de la API."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright no disponible (sin screenshots): %s", exc)
        return
    extra = {}
    libs = getattr(config, "PLAYWRIGHT_LD_LIBRARY_PATH", "")
    if libs:
        base = os.environ.get("LD_LIBRARY_PATH", "")
        extra["LD_LIBRARY_PATH"] = libs + (":" + base if base else "")
    fonts = getattr(config, "PLAYWRIGHT_FONTCONFIG_FILE", "")
    if fonts:
        extra["FONTCONFIG_FILE"] = fonts
    launch_env = {**os.environ, **extra} if extra else None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"],
                env=launch_env,
            )
            context = browser.new_context()
            page = context.new_page()
            try:
                for country, result in results.items():
                    try:
                        _capture_ui(page, country, result, out_dir, inspect)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("[%s] Captura UI falló: %s", country, exc)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo iniciar el navegador para screenshots: %s", exc)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def extract_all(only=None, mock=False, inspect=False, out_dir=None):
    """Extrae el Monitor de Ventas de los países indicados.

    Datos por API REST; screenshot por UI (best-effort). Nunca lanza: los
    fallos de datos quedan en `result.error` con `result.ok = False`.
    """
    countries = [c for c in config.COUNTRIES if not only or c in only]
    results = {c: MonitorResult(c) for c in countries}

    if mock:
        for c, result in results.items():
            result.ok = True
            result.stores = [
                {"tienda": "2", "ventas": 1516},
                {"tienda": "3", "ventas": 2307},
                {"tienda": "4", "ventas": 1513},
            ]
            result.ventas_total = sum(s["ventas"] for s in result.stores)
            result.refreshes = config.COUNTRIES[c].get("refresh_count", 1)
        return results

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    today = datetime.date.today()
    api_from = (today - datetime.timedelta(days=config.MONITOR_DAYS_BACK)).isoformat()
    api_to = today.isoformat()

    # 1) Datos: API REST del Monitor (una sesión con login reutilizado).
    session = None
    try:
        session = api_session()
    except Exception as exc:  # noqa: BLE001
        log.warning("Login del Monitor falló: %s", exc)
        for result in results.values():
            result.ok = False
            result.error = f"login Monitor: {str(exc)[:180]}"

    if session is not None:
        for country, result in results.items():
            log.info("[%s] Consultando VENTAS por API del Monitor...", country)
            try:
                result.stores = fetch_ventas(country, api_from, api_to, session)
                result.ventas_total = sum(s["ventas"] for s in result.stores)
                result.ok = True
                log.info("[%s] Monitor OK (ventas: %s, tiendas: %s)",
                         country, result.ventas_total, len(result.stores))
            except Exception as exc:  # noqa: BLE001
                result.ok = False
                result.error = str(exc)[:200]
                log.warning("[%s] Monitor falló: %s", country, exc)

    # 2) Screenshot: UI del Monitor (no bloquea los datos).
    if config.MONITOR_SEND_IMAGE or inspect:
        _capture_all_ui(results, out_dir, inspect)

    return results


# ---------------------------------------------------------------------------
# Formateo (parse_mode=HTML, igual que glpi_db)
# ---------------------------------------------------------------------------
def _esc(text):
    """Escapa caracteres reservados de HTML en Telegram."""
    return (str(text if text is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def format_monitor_message(results):
    """Mensaje HTML con los totales VENTAS por país. Vacío si no hay OK."""
    ok = [r for r in results.values() if r.ok]
    if not ok:
        return ""
    lines = ["📈 <b>Monitor de Ventas EPA</b>"]
    for country, result in results.items():
        if not result.ok:
            continue
        meta = config.COUNTRIES[country]
        detalle = ", ".join(f"{s['tienda']}={s['ventas']}" for s in result.stores) or "sin datos"
        lines.append(
            f"<b>{country}</b> ({meta['name']}): <b>{result.ventas_total}</b> ventas — {detalle}"
        )
    return "\n".join(lines)


def format_monitor_errors(results):
    """Mensaje de error (HTML) para Telegram. Vacío si todo salió bien."""
    failed = [r for r in results.values() if not r.ok]
    if not failed:
        return ""
    lines = ["⚠️ <b>Error en el Monitor de Ventas</b>"]
    for result in failed:
        lines.append(f"[{result.country}] {_esc(result.error or 'error desconocido')}")
    lines.append("Los reportes de tickets GLPI se enviaron normalmente.")
    return "\n".join(lines)


if __name__ == "__main__":
    config.setup_logging()
    res = extract_all(mock=True)
    assert set(res) == {"VE", "SV", "GT"}
    assert all(r.ok for r in res.values())
    assert "Monitor de Ventas EPA" in format_monitor_message(res)
    parsed = parse_ventas_counts(
        {"results": [[{"store": "2", "count": "1.516"}, {"store": "3", "count": 2307}]]}
    )
    assert parsed == [{"tienda": "2", "ventas": 1516}, {"tienda": "3", "ventas": 2307}], parsed
    print("monitor OK")
