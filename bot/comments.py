"""Stündlich: deine Telegram-Freigaben abarbeiten, dann neue Kommentare als Entwurf schicken."""
import sys
import traceback
from datetime import datetime, timedelta, timezone

import claude
import insta
import store
import telegram
from config import MAX_DRAFTS_PER_RUN, TABU, TG_CHAT

SYSTEM_ANTWORT = f"""Du antwortest als Betreiber eines deutschen Accounts für unpopuläre Meinungen auf Instagram-Kommentare.

Stil: kurz (max. 200 Zeichen), schlagfertig, freundlich-frech, Du-Ansprache, kein Gendern. Du bleibst bei der Meinung, darfst aber zugeben, wenn ein Argument gut ist. Nie beleidigend, keine erfundenen Fakten, keine Ratschläge zu Gesundheit, Geld oder Recht. Themen, die du nie anfasst: {"; ".join(TABU)}.

Empfiehl „ignorieren“ bei Spam, Werbung, Beleidigungen, Hass, Provokationen zu Tabu-Themen oder wenn eine Antwort nichts bringt.

Antworte ausschließlich mit JSON: {{"empfehlung": "antworten" oder "ignorieren", "antwort": "...", "grund": "kurz"}}"""


def senden(row, text):
    try:
        insta.reply(row["comment_id"], text)
    except Exception as e:  # z. B. Kommentar inzwischen gelöscht
        store.update("comment_drafts", {"id": row["id"]}, {"status": "failed"})
        return f"❌ Senden fehlgeschlagen: {telegram.esc(str(e))[:200]}"
    store.update("comment_drafts", {"id": row["id"]}, {"status": "sent", "draft": text})
    return "✅ Gesendet"


def freigaben_abarbeiten():
    offset = int((store.get_setting("tg_offset") or {}).get("value") or 0)
    for u in telegram.updates(offset):
        offset = u["update_id"] + 1

        if "callback_query" in u:
            cq = u["callback_query"]
            msg = cq.get("message", {})
            if str(msg.get("chat", {}).get("id")) != TG_CHAT:
                continue
            aktion, _, did = cq.get("data", "").partition(":")
            rows = store.select("comment_drafts", f"id=eq.{did}")
            if not rows or rows[0]["status"] != "pending":
                telegram.answer_callback(cq["id"], "Schon erledigt")
                continue
            row = rows[0]
            alt = telegram.esc(msg.get("text", ""))
            if aktion == "ok" and row["draft"]:
                ergebnis = senden(row, row["draft"])
                telegram.edit(msg["message_id"], f"{alt}\n\n{ergebnis}")
            elif aktion == "no":
                store.update("comment_drafts", {"id": row["id"]}, {"status": "ignored"})
                telegram.edit(msg["message_id"], f"{alt}\n\n🗑 Ignoriert")
            telegram.answer_callback(cq["id"])

        elif "message" in u:
            msg = u["message"]
            if str(msg.get("chat", {}).get("id")) != TG_CHAT:
                continue
            bezug = msg.get("reply_to_message")
            text = (msg.get("text") or "").strip()
            if not bezug or not text:
                continue
            rows = store.select("comment_drafts", f"telegram_message_id=eq.{bezug['message_id']}")
            if not rows or rows[0]["status"] != "pending":
                continue
            telegram.send(senden(rows[0], text), reply_to=msg["message_id"])

    store.set_setting("tg_offset", offset)


def neue_kommentare():
    ich = insta.me()["username"]
    hooks = {p["ig_media_id"]: (p["nummer"], p["hook"])
             for p in store.select("posts", "select=nummer,hook,ig_media_id&order=id.desc&limit=30")}
    grenze = datetime.now(timezone.utc) - timedelta(days=7)
    neu = 0
    for m in insta.recent_media(10):
        bekannt = {r["comment_id"] for r in
                   store.select("comment_drafts", f"media_id=eq.{m['id']}&select=comment_id")}
        for c in insta.comments(m["id"]):
            if c["id"] in bekannt or c.get("username") == ich:
                continue
            zeit = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if zeit < grenze:
                continue
            if neu >= MAX_DRAFTS_PER_RUN:
                return
            nummer, hook = hooks.get(m["id"], ("?", (m.get("caption") or "")[:90]))
            e = claude.ask_json(SYSTEM_ANTWORT, (
                f"Post: {hook}\n\nKommentar von @{c.get('username')}: {c.get('text')}"), max_tokens=400)
            ignorieren = e.get("empfehlung") == "ignorieren" or not e.get("antwort")
            row = store.insert("comment_drafts", {
                "comment_id": c["id"], "media_id": m["id"], "username": c.get("username"),
                "comment_text": c.get("text"), "draft": None if ignorieren else e["antwort"]})
            kopf = (f"💬 <b>#{nummer}</b> „{telegram.esc(hook)}“\n\n"
                    f"<b>@{telegram.esc(c.get('username'))}:</b> {telegram.esc(c.get('text'))}\n\n")
            if ignorieren:
                text = kopf + f"Vorschlag: ignorieren ({telegram.esc(e.get('grund', ''))})"
                knoepfe = [("🗑 Ignorieren", f"no:{row['id']}")]
            else:
                text = kopf + f"<b>Vorschlag:</b> {telegram.esc(e['antwort'])}"
                knoepfe = [("✅ Freigeben", f"ok:{row['id']}"), ("🗑 Ignorieren", f"no:{row['id']}")]
            text += "\n\n<i>Ändern: auf diese Nachricht mit deinem Text antworten.</i>"
            mid = telegram.send(text, buttons=knoepfe)
            store.update("comment_drafts", {"id": row["id"]}, {"telegram_message_id": mid})
            neu += 1


def main():
    if not telegram.aktiv():
        print("Telegram nicht eingerichtet – Kommentar-Begleitung pausiert.")
        return
    freigaben_abarbeiten()
    neue_kommentare()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        try:
            letzter = store.get_setting("alarm_kommentare")
            alt = letzter and datetime.fromisoformat(letzter["updated_at"].replace("Z", "+00:00"))
            if not alt or datetime.now(timezone.utc) - alt > timedelta(hours=6):
                store.set_setting("alarm_kommentare", "1")
                telegram.send(f"🚨 <b>Kommentar-Lauf fehlgeschlagen</b>\n{telegram.esc(str(e))[:900]}")
        except Exception:
            telegram.send(f"🚨 <b>Kommentar-Lauf fehlgeschlagen</b>\n{telegram.esc(str(e))[:900]}")
        sys.exit(1)
