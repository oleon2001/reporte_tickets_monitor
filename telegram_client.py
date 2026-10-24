"""
Cliente mínimo de Telegram (sendMessage / sendPhoto).

Envía al grupo configurado en .env (TG_BOT_TOKEN / TG_CHAT_ID). Si el envío con
Markdown falla (caracteres especiales en títulos de tickets), reintenta sin
formato para no perder el mensaje.
"""
import logging

import requests

import config

log = logging.getLogger(__name__)

TG_MAX_LEN = 4096


class TelegramError(Exception):
    """Error controlado de envío a Telegram."""


def _api(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def _check_config():
    if not config.TELEGRAM_BOT_TOKEN:
        raise TelegramError("Falta TG_BOT_TOKEN en el archivo .env")


def split_message(text, limit=TG_MAX_LEN):
    """Divide un texto en trozos <= limit, cortando por líneas."""
    if len(text) <= limit:
        return [text]
    chunks = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = line if not current else f"{current}\n{line}"
    if current:
        chunks.append(current)
    return chunks


def send_message(text, chat_id=None, parse_mode="HTML"):
    """Envía texto a un chat (por defecto el grupo). Divide en trozos si hace falta.

    Usa HTML (más robusto que Markdown con títulos de tickets). Si el envío con
    formato falla, reintenta sin formato para no perder el mensaje.
    """
    _check_config()
    target = chat_id or config.TELEGRAM_CHAT_ID
    if not target:
        raise TelegramError("Falta TG_CHAT_ID en el archivo .env")

    response = None
    for chunk in split_message(text):
        for mode in (parse_mode, None):
            payload = {
                "chat_id": target,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if mode:
                payload["parse_mode"] = mode
            resp = requests.post(_api("sendMessage"), json=payload, timeout=30)
            if resp.ok:
                response = resp.json()
                break
            if mode is None:
                raise TelegramError(f"sendMessage falló: {resp.text[:300]}")
            log.warning("sendMessage con %s falló, reintentando sin formato: %s",
                        mode, resp.text[:200])
    return response


def send_photo(path, caption="", chat_id=None):
    """Envía una imagen (screenshot) con pie de foto opcional."""
    _check_config()
    target = chat_id or config.TELEGRAM_CHAT_ID
    if not target:
        raise TelegramError("Falta TG_CHAT_ID en el archivo .env")
    try:
        with open(path, "rb") as fh:
            resp = requests.post(
                _api("sendPhoto"),
                data={"chat_id": target, "caption": caption[:1024]},
                files={"photo": fh},
                timeout=90,
            )
    except OSError as exc:
        raise TelegramError(f"No se pudo leer la imagen {path}: {exc}") from exc
    if not resp.ok:
        raise TelegramError(f"sendPhoto falló: {resp.text[:300]}")
    return resp.json()


if __name__ == "__main__":
    import config as _c
    _c.setup_logging()
    print("telegram_client OK")
