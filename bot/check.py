"""Setup-Check: prüft jeden Zugang einzeln und schickt eine Probe-Slide per Telegram."""
import os
import sys
import tempfile

import requests
from PIL import Image

import config
import store
import telegram

ergebnisse = []


def pruefe(name, fn):
    try:
        info = fn()
        ergebnisse.append((True, name, info or ""))
    except Exception as e:
        ergebnisse.append((False, name, str(e)[:300]))


def secrets():
    fehlt = [n for n in ["ANTHROPIC_API_KEY", "IG_ACCESS_TOKEN", "SUPABASE_URL", "SUPABASE_KEY",
                         "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"] if not config.env(n)]
    if fehlt:
        raise RuntimeError("Fehlende Secrets: " + ", ".join(fehlt))


def supabase():
    store.select("posts", "select=id&limit=1")
    store.select("comment_drafts", "select=id&limit=1")
    store.set_setting("setup_check", "ok")
    testbild = os.path.join(tempfile.mkdtemp(), "test.jpg")
    Image.new("RGB", (64, 80), (232, 182, 28)).save(testbild, "JPEG")
    url = store.upload(testbild, "check/test.jpg")
    if requests.get(url, timeout=30).status_code != 200:
        raise RuntimeError("Bucket 'slides' ist nicht öffentlich")
    return "Tabellen und Bildablage ok"


def instagram():
    import insta
    m = insta.me()
    return f"@{m['username']} (ID {m['user_id']})"


def telegram_chat():
    if not config.TG_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN fehlt")
    if not config.TG_CHAT:
        ids = {str(u["message"]["chat"]["id"]) for u in telegram.updates(0) if "message" in u}
        raise RuntimeError("TELEGRAM_CHAT_ID fehlt. Schreib deinem Bot kurz 'Hallo' und starte den Check neu. "
                           f"Gefundene Chat-IDs: {', '.join(ids) or 'keine'}")
    telegram.send("👋 Setup-Check: Telegram funktioniert.")
    return "Nachricht geschickt"


def probelauf():
    import daily
    from render import render
    post = daily.erzeugen(daily.topf_waehlen([]), [])
    post["nummer"] = 0
    dateien = render(post, tempfile.mkdtemp())
    telegram.send_photo(dateien[0], f"Probe-Slide: {post['hook']}")
    return post["hook"]


pruefe("Secrets vollständig", secrets)
pruefe("Supabase", supabase)
pruefe("Instagram", instagram)
pruefe("Telegram", telegram_chat)
pruefe("Claude + Rendering (Probe-Slide)", probelauf)

print("\n===== SETUP-CHECK =====")
for ok, name, info in ergebnisse:
    print(f"{'✅' if ok else '❌'} {name}: {info}")
alles_ok = all(ok for ok, _, _ in ergebnisse)
print("\nAlles bereit – der Bot kann loslegen." if alles_ok else "\nBitte die ❌-Punkte beheben und Check neu starten.")
try:
    telegram.send("✅ Setup-Check komplett bestanden." if alles_ok else
                  "⚠️ Setup-Check mit Fehlern – Details im GitHub-Log.")
except Exception:
    pass
sys.exit(0 if alles_ok else 1)
