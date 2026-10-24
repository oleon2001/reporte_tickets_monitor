"""
Registro de integrantes del grupo para recibir sus tickets por privado.

Publica un botón en el grupo; al pulsarlo se abre el bot y, tras pulsar Start,
el bot pide al integrante su usuario de GLPI (o su nombre) y guarda el mapeo
`login -> chat_id` en telegram_members.json, que config.py lee automáticamente.

Uso:
    python telegram_register.py --post            # publica el botón en el grupo
    python telegram_register.py --listen 1800     # escucha 30 min y guarda altas
    python telegram_register.py --list            # muestra los registrados
    python telegram_register.py                   # post + escucha 10 min
"""
import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata

import requests

import config
import glpi_db
from telegram_client import _api

log = logging.getLogger("tg_register")
MEMBERS_PATH = os.path.join(config.BASE_DIR, "telegram_members.json")
BOT_URL = f"https://t.me/{config.TELEGRAM_BOT_USERNAME}"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def api(method, **params):
    resp = requests.get(_api(method), params=params, timeout=60)
    return resp.json()


def reply(chat_id, text):
    try:
        requests.post(_api("sendMessage"), json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo responder a %s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Persistencia de miembros
# ---------------------------------------------------------------------------
def load_members():
    if os.path.exists(MEMBERS_PATH):
        try:
            with open(MEMBERS_PATH, encoding="utf-8") as fh:
                return {str(k): str(v) for k, v in json.load(fh).items()}
        except (ValueError, OSError):
            return {}
    return {}


def save_members(members):
    with open(MEMBERS_PATH, "w", encoding="utf-8") as fh:
        json.dump(members, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Botón en el grupo
# ---------------------------------------------------------------------------
def post_button():
    text = (
        "📣 <b>Activa tus alertas de tickets</b>\n\n"
        "Si eres técnico, pulsa el botón para recibir por privado tus casos "
        "vencidos, próximos a vencer y al 70%."
    )
    markup = {"inline_keyboard": [[
        {"text": "📲 Activar mis alertas", "url": f"{BOT_URL}?start=alta"}
    ]]}
    resp = requests.post(_api("sendMessage"), json={
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
    }, timeout=30)
    data = resp.json()
    if not data.get("ok"):
        print("ERROR al publicar el botón:", data)
        return False
    print("Botón publicado en el grupo:", BOT_URL)
    return True


# ---------------------------------------------------------------------------
# Escucha de registros
# ---------------------------------------------------------------------------
def _norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def _match_login(text, users):
    """Empareja el texto con un usuario de GLPI; devuelve su login o None."""
    target = _norm(text)
    if not target:
        return None
    tokens = set(target.split())
    best, best_score = None, 0.0
    for user in users:
        login = str(user.get("login") or "")
        if _norm(login) == target:
            return login
        name_tokens = set(_norm(user.get("nombre")).split())
        if not name_tokens:
            continue
        score = len(tokens & name_tokens) / len(name_tokens)
        if score > best_score:
            best, best_score = login, score
    return best if best_score >= 0.5 else None


def listen(seconds=600):
    members = load_members()
    users = []
    try:
        users = glpi_db.list_group_users()
        print(f"Usuarios de GLPI en el grupo: {len(users)}")
    except Exception as exc:  # noqa: BLE001
        print(f"Aviso: no se pudo leer usuarios de GLPI ({exc}). Se empareja por texto.")

    # Drenar updates viejos para no reprocesarlos.
    offset = None
    try:
        r = api("getUpdates", offset=-1, limit=1,
                allowed_updates=json.dumps(["message"]))
        if r.get("result"):
            offset = r["result"][-1]["update_id"] + 1
    except Exception:  # noqa: BLE001
        pass

    deadline = time.time() + seconds
    print(f"Escuchando {seconds}s... (registrados: {len(members)})")
    while time.time() < deadline:
        try:
            r = api("getUpdates", offset=offset, timeout=50,
                    allowed_updates=json.dumps(["message"]))
        except Exception as exc:  # noqa: BLE001
            log.warning("poll error: %s", exc)
            time.sleep(3)
            continue
        for update in r.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg or msg.get("chat", {}).get("type") != "private":
                continue
            chat_id = str(msg["chat"]["id"])
            frm = msg.get("from", {})
            name = f"{frm.get('first_name', '')} {frm.get('last_name', '')}".strip()
            text = (msg.get("text") or "").strip()

            if text.startswith("/start"):
                reply(chat_id,
                      f"👋 Hola {name or ''}.\n"
                      "Para enviarte tus tickets por privado, respóndeme con tu "
                      "<b>usuario de GLPI</b> (ej: 28492679) o tu nombre tal como "
                      "aparece en GLPI.")
                continue
            if not text:
                continue

            login = _match_login(text, users) or text.strip()
            members[login] = chat_id
            save_members(members)
            matched = next((u for u in users if str(u.get("login")) == str(login)), None)
            pretty = matched["nombre"].strip() if matched else login
            reply(chat_id, f"✅ Registrado como <b>{login}</b> ({pretty}). "
                           "Recibirás tus tickets aquí.")
            print(f"REGISTRADO: {login} <- chat_id {chat_id} ({name})")

    print("Registrados actuales:", json.dumps(members, ensure_ascii=False))
    return members


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    config.setup_logging()
    parser = argparse.ArgumentParser(description="Registro de integrantes (Telegram)")
    parser.add_argument("--post", action="store_true", help="publica el botón en el grupo")
    parser.add_argument("--listen", type=int, default=0, metavar="SEGUNDOS",
                        help="escucha durante N segundos y guarda altas")
    parser.add_argument("--list", action="store_true", help="muestra los registrados")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(load_members(), ensure_ascii=False, indent=2))
        return 0

    if args.post or not (args.post or args.listen):
        post_button()
    if args.listen:
        listen(args.listen)
    elif not args.post:
        listen(600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
