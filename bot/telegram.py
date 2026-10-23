"""Telegram-Bot: Meldungen an dich und deine Freigaben zurück."""
import html
import json

import requests

from config import TG_CHAT, TG_TOKEN

API = f"https://api.telegram.org/bot{TG_TOKEN}"


def aktiv():
    return bool(TG_TOKEN and TG_CHAT)


def esc(text):
    return html.escape(text or "")


def send(text, buttons=None, reply_to=None):
    if not aktiv():
        print("[Telegram aus]", text)
        return None
    data = {"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    r = requests.post(f"{API}/sendMessage", json=data, timeout=30)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def send_photo(path, caption=""):
    if not aktiv():
        return
    with open(path, "rb") as f:
        requests.post(f"{API}/sendPhoto", data={"chat_id": TG_CHAT, "caption": caption},
                      files={"photo": f}, timeout=60).raise_for_status()


def send_album(pfade, caption=""):
    """Schickt bis zu 10 Bilder als ein Album – so kommt das Karussell am Stück an."""
    if not aktiv():
        print("[Telegram aus] Album:", pfade)
        return
    dateien, medien = {}, []
    for i, p in enumerate(pfade[:10]):
        name = f"bild{i}"
        dateien[name] = open(p, "rb")
        eintrag = {"type": "photo", "media": f"attach://{name}"}
        if i == 0 and caption:
            eintrag.update(caption=caption, parse_mode="HTML")
        medien.append(eintrag)
    try:
        r = requests.post(f"{API}/sendMediaGroup", timeout=120,
                          data={"chat_id": TG_CHAT, "media": json.dumps(medien)}, files=dateien)
        r.raise_for_status()
    finally:
        for f in dateien.values():
            f.close()


def edit(message_id, text):
    requests.post(f"{API}/editMessageText", timeout=30, json={
        "chat_id": TG_CHAT, "message_id": message_id, "text": text, "parse_mode": "HTML"})


def answer_callback(cb_id, text=""):
    try:
        requests.post(f"{API}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": text}, timeout=15)
    except requests.RequestException:
        pass  # alte Klicks lassen sich nicht mehr beantworten – egal


def updates(offset):
    r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])
