"""
Configuración central del reporte de tickets GLPI.

Los valores sensibles se cargan desde .env (variables de entorno).
"""
import json
import logging
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env(name, default=None):
    """Variable de entorno, o el default si no está definida o está vacía.

    Un valor vacío (p. ej. `GLPI_DB_PASSWORD=`) NO debe pisar el default:
    se trata igual que "no definido".
    """
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value


def _env_int(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=True):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _env_members(name):
    """Mapeo técnico -> chat_id de Telegram.

    Fuentes (se combinan):
      1. .env: TG_MEMBERS con formato "login:chat_id,login2:chat_id2"
         o JSON: {"login": "chat_id"}.
      2. Archivo telegram_members.json en la carpeta del proyecto.

    La clave puede ser el login de GLPI (recomendado) o el nombre del técnico.
    """
    members = {}
    raw = os.getenv(name, "").strip()
    if raw:
        if raw.startswith("{"):
            try:
                members.update({str(k): str(v) for k, v in json.loads(raw).items()})
            except ValueError:
                logging.getLogger(__name__).warning(
                    "%s no es JSON válido; se ignora el valor del .env", name
                )
        else:
            for pair in raw.split(","):
                if ":" not in pair:
                    continue
                key, value = pair.split(":", 1)
                key, value = key.strip(), value.strip()
                if key and value:
                    members[key] = value

    path = os.path.join(BASE_DIR, "telegram_members.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                members.update({str(k): str(v) for k, v in json.load(fh).items()})
        except (ValueError, OSError) as exc:
            logging.getLogger(__name__).warning(
                "No se pudo leer telegram_members.json: %s", exc
            )
    return members


# =========================================================================
# GENERAL
# =========================================================================
TIMEZONE = _env("TIMEZONE", "America/Caracas")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_DIR = os.path.join(BASE_DIR, "logs")
OUTPUT_DIR = os.path.join(BASE_DIR, "salidas")


# =========================================================================
# GLPI (MySQL)
# =========================================================================
GLPI_DB = {
    "host": _env("GLPI_DB_HOST", "10.48.63.60"),
    "port": _env_int("GLPI_DB_PORT", 3306),
    "user": _env("GLPI_DB_USER", "glpi_rpt"),
    "password": _env("GLPI_DB_PASSWORD", ""),
    "database": _env("GLPI_DB_NAME", "glpidb"),
}


# =========================================================================
# TELEGRAM
# =========================================================================
TELEGRAM_BOT_TOKEN = _env("TG_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _env("TG_CHAT_ID", "")

# Nombre de usuario del bot (sin @) para el enlace del botón de registro.
TELEGRAM_BOT_USERNAME = _env("TG_BOT_USERNAME", "Reportes_glpi_bot")

# Técnico -> chat_id de Telegram. Ver _env_members().
TELEGRAM_MEMBERS = _env_members("TG_MEMBERS")


# =========================================================================
# GLPI (reportes)
# =========================================================================
# Grupo de GLPI (glpi_groups_users.groups_id) cuyos tickets se reportan.
GLPI_GROUP_ID = _env_int("GLPI_GROUP_ID", 11)

# Horas de anticipación para el reporte "próximos a vencer".
NEAR_DUE_HOURS = _env_int("NEAR_DUE_HOURS", 24)

# URL base de GLPI para enlazar cada ticket (vacío = sin enlaces).
GLPI_BASE_URL = _env("GLPI_BASE_URL", "")

# Gráfica PNG (barras por técnico + pastel de totales) enviada al grupo.
SEND_CHART = _env_bool("SEND_CHART", True)


# =========================================================================
# MONITOR DE VENTAS (EPA)
# =========================================================================
MONITOR_BASE_URL = _env("MONITOR_BASE_URL", "http://10.48.12.77:3500")
MONITOR_DATE_FORMAT = "%d/%m/%Y"          # la UI usa DD/MM/YYYY
MONITOR_DAYS_BACK = _env_int("MONITOR_DAYS_BACK", 1)  # rango: ayer -> hoy
MONITOR_SEND_IMAGE = _env_bool("MONITOR_SEND_IMAGE", True)  # adjuntar screenshot

# Tiempo de espera (ms) para que las tarjetas del Monitor rendericen.
MONITOR_RENDER_TIMEOUT_MS = _env_int("MONITOR_RENDER_TIMEOUT_MS", 20000)

MONITOR_SELECTORS = {
    "date_from": "input[placeholder='DD/MM/YYYY']",
    "date_to": "input[placeholder='DD/MM/YYYY']",
    "refresh": "button:has-text('Actualizar')",
}

# API REST del Monitor: fuente de datos robusta de las VENTAS (igual que
# reporte_joseph). La UI de arriba se usa solo para el screenshot.
MONITOR_API_URL = _env("MONITOR_API_URL", "http://10.48.12.77:3010")
MONITOR_API_USER = _env("MONITOR_API_USER", "EpaSupport2023")
MONITOR_API_PASS = _env("MONITOR_API_PASS", "vJ69@GP8PSlapqh@JCXDbz!U8iE5VV%@o5")
MONITOR_API_TIMEOUT = _env_int("MONITOR_API_TIMEOUT", 45)
MONITOR_API_LIMIT = _env_int("MONITOR_API_LIMIT", 200)
# Endpoint que devuelve el conteo por tienda de la columna VENTAS del Monitor.
MONITOR_VENTAS_ENDPOINT = _env("MONITOR_VENTAS_ENDPOINT", "transaction-ventas-front-count")

# Ruta a librerías de sistema para el navegador de Playwright. Se usa cuando el
# host no tiene las libs instaladas (sin sudo) y se extrajeron en una carpeta.
PLAYWRIGHT_LD_LIBRARY_PATH = _env("PLAYWRIGHT_LD_LIBRARY_PATH", "")

# Archivo fonts.conf para el navegador (fontconfig). Necesario en hosts sin
# configuración de fuentes (sin sudo): apunta a un fonts.conf propio.
PLAYWRIGHT_FONTCONFIG_FILE = _env("PLAYWRIGHT_FONTCONFIG_FILE", "")

# Países del Monitor. `refresh_count` = cuántas veces refrescar antes de capturar.
# SV requiere 2 refresh: con la herramienta no renderiza bien a la primera.
COUNTRIES = {
    "VE": {"name": "Venezuela", "monitor_path": "/ve", "refresh_count": 1},
    "SV": {"name": "El Salvador", "monitor_path": "/sv", "refresh_count": 2},
    "GT": {"name": "Guatemala", "monitor_path": "/gt", "refresh_count": 1},
}


# =========================================================================
# LOGGING
# =========================================================================
def setup_logging():
    logging.basicConfig(
        level=getattr(logging, str(LOG_LEVEL or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


if __name__ == "__main__":
    setup_logging()
    print("config OK")
    print(f"  Monitor: {MONITOR_BASE_URL}")
    print(f"  Monitor API: {MONITOR_API_URL}")
    print(f"  Países: {', '.join(COUNTRIES)}")
    print(f"  SV refresh_count: {COUNTRIES['SV']['refresh_count']}")
    print(f"  Próximos a vencer: <={NEAR_DUE_HOURS}h")
    print(f"  Grupo GLPI: {GLPI_GROUP_ID}")
    print(f"  Gráfica PNG: {'sí' if SEND_CHART else 'no'}")
    print(f"  Miembros Telegram configurados: {len(TELEGRAM_MEMBERS)}")
