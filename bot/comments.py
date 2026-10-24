"""Alle 30 Minuten: deine Telegram-Freigaben abarbeiten, dann neue Kommentare als Entwurf schicken."""
import json
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


def post_freigabe(aktion, entwurf_id, msg, cb_id):
    """Verarbeitet die Knöpfe unter einem Post-Entwurf: posten, verwerfen, neu erzeugen."""
    rows = store.select("post_drafts", f"id=eq.{entwurf_id}")
    if not rows:
        print(f"Kein Post-Entwurf mit id {entwurf_id}")
        telegram.answer_callback(cb_id, "Entwurf nicht gefunden")
        telegram.send(f"⚠️ Zu diesem Entwurf (id {entwurf_id}) finde ich nichts mehr. "
                      f"Nutze <b>Actions → Entwurf freigeben</b>.")
        return
    if rows[0]["status"] != "pending":
        print(f"Entwurf {entwurf_id} ist bereits '{rows[0]['status']}'")
        telegram.answer_callback(cb_id, "Schon erledigt")
        return
    entwurf = rows[0]
    alt = telegram.esc(msg.get("text", ""))
    print(f"Bearbeite Entwurf {entwurf['id']} (#{entwurf['nummer']}) mit Aktion {aktion}")

    if aktion == "pok":
        try:
            urls = [u for u in entwurf["bild_urls"].split("\n") if u.strip()]
            media_id = insta.publish_carousel(urls, entwurf["caption"])
        except Exception as e:
            print("Posten fehlgeschlagen:", repr(e))
            telegram.answer_callback(cb_id, "Fehlgeschlagen")
            telegram.send(f"❌ <b>Post #{entwurf['nummer']} konnte nicht veröffentlicht werden</b>\n"
                          f"{telegram.esc(str(e))[:600]}\n\n"
                          f"Der Entwurf bleibt stehen, du kannst es erneut versuchen.")
            return
        import daily as _d
        _d.ersten_kommentar_posten(media_id, entwurf.get("post_json"))
        store.insert("posts", {"nummer": entwurf["nummer"], "topf": entwurf["topf"],
                               "hook": entwurf["hook"], "caption": entwurf["caption"],
                               "ig_media_id": media_id})
        store.update("post_drafts", {"id": entwurf["id"]}, {"status": "published"})
        print("Veröffentlicht:", media_id)
        telegram.edit(msg["message_id"], f"{alt}\n\n✅ Ist online")

    elif aktion == "pno":
        store.update("post_drafts", {"id": entwurf["id"]}, {"status": "rejected"})
        telegram.edit(msg["message_id"], f"{alt}\n\n🗑 Verworfen – heute kommt nichts mehr")

    elif aktion == "pneu":
        store.update("post_drafts", {"id": entwurf["id"]}, {"status": "rejected"})
        telegram.edit(msg["message_id"], f"{alt}\n\n🔄 Verworfen, neuer Vorschlag folgt")
        telegram.answer_callback(cb_id, "Einen Moment …")
        neuer_vorschlag(entwurf)
        return

    telegram.answer_callback(cb_id)


def _bauen_und_schicken(nummer, topf, post, titel):
    """Rendert, lädt hoch und schickt einen Entwurf nach Telegram."""
    import tempfile

    import daily
    from render import render
    post["nummer"] = nummer
    post["handle"] = "@" + insta.me()["username"]
    dateien = render(post, tempfile.mkdtemp())
    stempel = daily.jetzt().strftime("%Y%m%d-%H%M%S")
    urls = [store.upload(f, f"{nummer:04d}-{stempel}/{i + 1:02d}.jpg") for i, f in enumerate(dateien)]
    caption = post.get("caption_fertig") or daily.caption_bauen(post)
    return daily.entwurf_anlegen(nummer, topf, post, caption, urls, dateien, titel)


def neuer_vorschlag(alter_entwurf):
    """Erzeugt sofort einen neuen Entwurf mit derselben Nummer."""
    import daily
    try:
        historie = store.select("posts", "select=nummer,hook,topf&order=id.desc&limit=120")
        alte = [h["hook"] for h in historie] + [alter_entwurf["hook"]]
        post = daily.erzeugen(alter_entwurf["topf"], alte)
        _bauen_und_schicken(alter_entwurf["nummer"], alter_entwurf["topf"], post,
                            f"📝 <b>Neuer Entwurf für Post #{alter_entwurf['nummer']}</b>")
    except Exception as e:
        telegram.send(f"🚨 <b>Neuer Vorschlag fehlgeschlagen</b>\n{telegram.esc(str(e))[:600]}")


def post_bearbeiten(entwurf, text):
    """Antwort auf einen Entwurf: neue Bildunterschrift oder – mit 'Hook:' – neuer Spruch."""
    import daily
    if text.lower().startswith("hook:"):
        neuer_hook = text[5:].strip()
        if not neuer_hook:
            return "❌ Nach „Hook:“ stand kein Text."
        try:
            post = json.loads(entwurf.get("post_json") or "{}")
            if not post.get("argumente"):
                return "❌ Für diesen Entwurf fehlen die Originaldaten, nimm „Neuer Vorschlag“."
            post["hook"] = neuer_hook
            post["caption_fertig"] = entwurf["caption"]
            store.update("post_drafts", {"id": entwurf["id"]}, {"status": "rejected"})
            _bauen_und_schicken(entwurf["nummer"], entwurf["topf"], post,
                                f"📝 <b>Post #{entwurf['nummer']} mit deinem Hook</b>")
            return "✏️ Neue Slides sind unterwegs."
        except Exception as e:
            return f"❌ Neu rendern fehlgeschlagen: {telegram.esc(str(e))[:200]}"

    neue_caption = text.strip()
    store.update("post_drafts", {"id": entwurf["id"]}, {"caption": neue_caption})
    if entwurf.get("telegram_message_id"):
        telegram.edit(entwurf["telegram_message_id"],
                      f"„{telegram.esc(entwurf['hook'])}“\n\n"
                      f"<b>Bildunterschrift (von dir):</b>\n{telegram.esc(neue_caption)}")
    return "✏️ Bildunterschrift übernommen. Jetzt oben auf ✅ Posten tippen."


def offene_entwuerfe():
    return (store.select("post_drafts", "status=eq.pending&select=id")
            + store.select("comment_drafts", "status=eq.pending&select=id"))


def einsammeln():
    """Holt Telegram-Updates ab und legt sie in der Eingangstabelle ab.

    Telegram hält einen Knopfdruck nur kurz vor. Deshalb sammelt der Dienst
    tg-poll in Supabase jede Minute ein; dieser Durchgang hier ist nur die
    Rückfallebene, falls der einmal nicht läuft."""
    offset = int((store.get_setting("tg_offset") or {}).get("value") or 0)
    neuigkeiten = telegram.updates(offset)

    # Selbstheilung: Steht der Zähler zu hoch, überspringt Telegram jeden Klick
    # dauerhaft. Wenn nichts kommt, obwohl etwas auf Freigabe wartet, fragen wir
    # die ganze Warteschlange ab. Doppelte Einträge fängt der Schlüssel ab.
    if not neuigkeiten and offset and offene_entwuerfe():
        print(f"Keine Updates bei Zähler {offset}, obwohl Entwürfe warten – "
              f"frage die komplette Warteschlange ab.")
        neuigkeiten = telegram.updates(0)
        if neuigkeiten:
            print(f"Zähler war verklemmt, {len(neuigkeiten)} Update(s) nachgeholt.")

    for u in neuigkeiten:
        store.insert_ignore("tg_inbox", {"update_id": u["update_id"], "payload": u})
        offset = max(offset, u["update_id"] + 1)
    if neuigkeiten:
        store.set_setting("tg_offset", offset)


def ein_update(u):
    """Verarbeitet genau einen Eintrag: Knopfdruck oder Antwort-Nachricht."""
    if "callback_query" in u:
        cq = u["callback_query"]
        msg = cq.get("message", {})
        if str(msg.get("chat", {}).get("id")) != TG_CHAT:
            print(f"Klick aus fremdem Chat ignoriert: {msg.get('chat', {}).get('id')}")
            return
        aktion, _, did = cq.get("data", "").partition(":")
        print(f"Klick empfangen: {aktion}:{did}")

        if aktion.startswith("p"):          # Post-Entwurf statt Kommentar
            post_freigabe(aktion, did, msg, cq["id"])
            return

        rows = store.select("comment_drafts", f"id=eq.{did}")
        if not rows or rows[0]["status"] != "pending":
            print(f"Kein wartender Kommentar-Entwurf mit id {did}")
            telegram.answer_callback(cq["id"], "Schon erledigt")
            return
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
            return
        bezug = msg.get("reply_to_message")
        text = (msg.get("text") or "").strip()
        if not bezug or not text:
            return
        # Antwort auf einen Post-Entwurf?
        entwuerfe = store.select("post_drafts", f"telegram_message_id=eq.{bezug['message_id']}")
        if entwuerfe:
            if entwuerfe[0]["status"] != "pending":
                telegram.send("Dieser Entwurf ist schon erledigt.", reply_to=msg["message_id"])
                return
            telegram.send(post_bearbeiten(entwuerfe[0], text), reply_to=msg["message_id"])
            return

        rows = store.select("comment_drafts", f"telegram_message_id=eq.{bezug['message_id']}")
        if not rows or rows[0]["status"] != "pending":
            return
        telegram.send(senden(rows[0], text), reply_to=msg["message_id"])


def freigaben_abarbeiten():
    """Arbeitet ab, was in der Eingangstabelle liegt."""
    einsammeln()
    offen = store.select("tg_inbox", "verarbeitet=is.false&order=update_id.asc&limit=100")
    print(f"Eingangstabelle: {len(offen)} unerledigte(r) Eintrag/Einträge")

    for eintrag in offen:
        try:
            ein_update(eintrag["payload"])
        except Exception as fehler:   # ein kaputter Klick darf den Lauf nicht kippen
            traceback.print_exc()
            telegram.send(f"⚠️ Ein Klick ließ sich nicht ausführen:\n"
                          f"{telegram.esc(str(fehler))[:400]}\n\n"
                          f"Der Entwurf wartet weiter – nutze <b>Actions → Entwurf freigeben</b>.")
        store.update("tg_inbox", {"update_id": eintrag["update_id"]}, {"verarbeitet": True})

    # Erledigtes nach einer Woche räumen, damit die Tabelle nicht endlos wächst
    grenze = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.delete("tg_inbox", f"verarbeitet=is.true&created_at=lt.{grenze}")


def eroeffnungskommentare():
    """Die Kommentare, die der Account selbst unter seine Beiträge gesetzt hat.

    Sie sind der Kontext, auf den die Leute meist antworten – ohne sie liest sich
    ein Kommentar wie eine Antwort auf eine ungestellte Frage."""
    rows = store.select("comment_drafts",
                        "username=like.*eigener*&select=media_id,comment_text&order=id.asc")
    return {r["media_id"]: (r["comment_text"] or "") for r in rows}


def neue_kommentare():
    ich = insta.me()["username"]
    hooks = {p["ig_media_id"]: (p["nummer"], p["hook"])
             for p in store.select("posts", "select=nummer,hook,ig_media_id&order=id.desc&limit=30")}
    eroeffnung = eroeffnungskommentare()
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
            # Instagram gibt den Benutzernamen nicht immer heraus
            wer = c.get("username") or "jemand"
            mein_kommentar = eroeffnung.get(m["id"], "")
            try:
                frage = f"Post: {hook}\n"
                if mein_kommentar:
                    frage += f"\nDein eigener erster Kommentar darunter: {mein_kommentar}\n"
                frage += f"\nKommentar von {wer}: {c.get('text')}"
                e = claude.ask_json(SYSTEM_ANTWORT, frage, max_tokens=900)
            except claude.ApiFehler:
                raise
            except (ValueError, RuntimeError) as fehler:
                print(f"Entwurf für {c['id']} übersprungen: {fehler}")
                continue
            ignorieren = e.get("empfehlung") == "ignorieren" or not e.get("antwort")
            row = store.insert("comment_drafts", {
                "comment_id": c["id"], "media_id": m["id"], "username": c.get("username"),  # darf leer sein
                "comment_text": c.get("text"), "draft": None if ignorieren else e["antwort"]})
            kopf = f"💬 <b>#{nummer}</b> „{telegram.esc(hook)}“\n\n"
            if mein_kommentar:
                kopf += f"<i>Dein Einstieg: {telegram.esc(mein_kommentar)}</i>\n\n"
            kopf += f"<b>{telegram.esc(wer)}:</b> {telegram.esc(c.get('text'))}\n\n"
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
    offen = store.select("post_drafts", "status=eq.pending&select=id,nummer,hook")
    print(f"Wartende Post-Entwürfe: {[(e['id'], e['nummer']) for e in offen]}")
    freigaben_abarbeiten()
    neue_kommentare()
    danach = store.select("post_drafts", "status=eq.pending&select=id")
    print(f"Wartende Post-Entwürfe danach: {len(danach)}")


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
