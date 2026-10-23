"""Täglicher Post: Thema wählen → Meinung schreiben → prüfen → rendern → posten → melden.

Aufruf:
  python bot/daily.py          normaler Lauf (postet ab 18 Uhr, max. 1x pro Tag)
  python bot/daily.py --force  sofort posten
  python bot/daily.py --dry    nur erzeugen und rendern, nichts hochladen
"""
import os
import random
import re
import sys
import tempfile
import traceback
from datetime import datetime, timezone

import claude
import insta
import store
import telegram
from config import BERLIN, POST_FREIGABE, POST_HOUR, TABU, TOEPFE
from render import render

SYSTEM_AUTOR = f"""Du bist die Redaktion eines deutschen Instagram-Account für unpopuläre Meinungen.

Ziel: Eine Meinung, bei der ungefähr die Hälfte der Leute sofort widersprechen will – über harmlose Alltagsthemen. Streit ja, Verletzung nie.

Ton: frech, witzig, selbstbewusst, augenzwinkernd, nie gemein. Du-Ansprache. Kein Gendern. Deutsche Alltagssprache, gern mit regionalem Einschlag.

Niemals diese Themen: {"; ".join(TABU)}.

Regeln:
- Keine Fakten, Zahlen, Studien oder Zitate erfinden. Argumente sind Meinung, Beobachtung und Humor.
- Keine Emojis in hook, titel, text und cta_frage.
- Der hook steht allein auf der ersten Slide: ohne „Unpopuläre Meinung:“ davor, als klare Behauptung.
- Längen: hook max. 90 Zeichen, titel max. 45, text max. 150, cta_frage max. 28.
- caption: 2–3 kurze Sätze, die zum Kommentieren reizen, endet mit einer Frage. Emojis sparsam erlaubt.
- hashtags: 5–7 deutsche Hashtags ohne Leerzeichen.

Antworte ausschließlich mit JSON:
{{"hook": "...", "argumente": [{{"titel": "...", "text": "..."}}, {{"titel": "...", "text": "..."}}, {{"titel": "...", "text": "..."}}], "cta_frage": "...", "caption": "...", "hashtags": ["#...", "..."]}}"""

SYSTEM_PRUEFER = f"""Du prüfst Instagram-Posts eines Accounts für unpopuläre Meinungen vor der Veröffentlichung. Sei streng.

Nicht ok ist ein Post, wenn er
- eines dieser Themen berührt: {"; ".join(TABU)}
- beleidigt, abwertet oder diskriminiert
- zu riskantem oder gefährlichem Verhalten ermutigt
- Fakten, Zahlen, Studien oder Zitate behauptet, die erfunden sein könnten
- reale Personen, Marken oder Unternehmen nennt oder angreift
- rechtliche, medizinische oder finanzielle Ratschläge gibt
- inhaltlich einer bereits geposteten Meinung zu ähnlich ist

Antworte ausschließlich mit JSON: {{"ok": true/false, "grund": "kurz"}}"""


def jetzt():
    return datetime.now(BERLIN)


def heute_schon_gepostet():
    """Zählt veröffentlichte Posts und wartende Entwürfe – beides heißt: heute ist erledigt."""
    start = (jetzt().replace(hour=0, minute=0, second=0, microsecond=0)
             .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if store.select("posts", f"created_at=gte.{start}&select=id"):
        return True
    return bool(store.select("post_drafts", f"created_at=gte.{start}&status=eq.pending&select=id"))


def topf_waehlen(historie):
    benutzt = [h.get("topf") for h in historie]  # neueste zuerst
    kandidaten = TOEPFE[:]
    random.shuffle(kandidaten)
    return max(kandidaten, key=lambda t: benutzt.index(t) if t in benutzt else 10**6)


def laengen_ok(p):
    try:
        return (len(p["hook"]) <= 110 and len(p["argumente"]) == 3
                and all(len(a["titel"]) <= 60 and len(a["text"]) <= 180 for a in p["argumente"])
                and len(p["cta_frage"]) <= 40 and p["caption"])
    except (KeyError, TypeError):
        return False


def erzeugen(topf, alte_hooks, versuche=5):
    liste = "\n".join(f"- {h}" for h in alte_hooks[:120]) or "- (noch keine)"
    gruende = []
    for _ in range(versuche):
        try:
            post = claude.ask_json(SYSTEM_AUTOR, (
                f"Themenbereich heute: {topf}.\n\n"
                f"Diese Meinungen gab es schon – nicht wiederholen, auch nicht sinngemäß:\n{liste}\n\n"
                "Liefere eine neue."))
            if not laengen_ok(post):
                gruende.append("Format/Längen daneben")
                continue
            urteil = claude.ask_json(SYSTEM_PRUEFER, (
                f"Neuer Post:\n{post}\n\nBereits gepostete Meinungen:\n{liste}"), max_tokens=800)
        except (ValueError, RuntimeError) as e:
            # Unsauberes JSON oder ein Aussetzer der API kostet nur diesen Versuch,
            # nicht den ganzen Lauf.
            gruende.append(f"Antwort unbrauchbar: {str(e)[:120]}")
            continue
        if urteil.get("ok") is True:
            return post
        gruende.append(urteil.get("grund", "abgelehnt"))
    raise RuntimeError("Kein sicherer Post zustande gekommen: " + " | ".join(gruende))


def caption_bauen(post):
    tags = []
    for t in post.get("hashtags", [])[:7] + ["#senfdazu", "#unpopuläremeinung"]:
        t = "#" + re.sub(r"[^\wäöüÄÖÜß]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    return f"{post['caption'].strip()}\n\n{' '.join(tags)}\n\nKI-generiert."


def main():
    dry = "--dry" in sys.argv
    force = "--force" in sys.argv or os.environ.get("FORCE") == "1"

    if not (dry or force):
        if jetzt().hour < POST_HOUR:
            print("Noch zu früh – der Post kommt im nächsten Lauf.")
            return
        if heute_schon_gepostet():
            print("Heute ist schon gepostet.")
            return

    if not dry:
        if insta.refresh_if_needed():
            print("Instagram-Token erneuert.")

    historie = store.select("posts", "select=nummer,hook,topf&order=id.desc&limit=120") if not dry else []
    nummer = (historie[0]["nummer"] + 1) if historie else 1
    topf = topf_waehlen(historie)
    print(f"Post #{nummer} – Thema: {topf}")

    post = erzeugen(topf, [h["hook"] for h in historie])
    post["nummer"] = nummer
    if not dry:
        post["handle"] = "@" + insta.me()["username"]  # Name kommt immer aktuell von Instagram
    print("Hook:", post["hook"])

    ordner = "out" if dry else tempfile.mkdtemp()
    dateien = render(post, ordner)
    if dry:
        print("Probelauf fertig:", dateien)
        return dateien, post

    stempel = jetzt().strftime("%Y%m%d-%H%M")
    urls = [store.upload(f, f"{nummer:04d}-{stempel}/{i + 1:02d}.jpg") for i, f in enumerate(dateien)]
    caption = caption_bauen(post)

    if POST_FREIGABE:
        entwurf = store.insert("post_drafts", {
            "nummer": nummer, "topf": topf, "hook": post["hook"],
            "caption": caption, "bild_urls": "\n".join(urls)})
        telegram.send_album(dateien, f"📝 <b>Entwurf für Post #{nummer}</b> · {telegram.esc(topf)}")
        mid = telegram.send(
            f"„{telegram.esc(post['hook'])}“\n\n<b>Bildunterschrift:</b>\n{telegram.esc(caption)}",
            buttons=[("✅ Posten", f"pok:{entwurf['id']}"),
                     ("🔄 Neuer Vorschlag", f"pneu:{entwurf['id']}"),
                     ("🗑 Verwerfen", f"pno:{entwurf['id']}")])
        store.update("post_drafts", {"id": entwurf["id"]}, {"telegram_message_id": mid})
        print("Entwurf wartet auf deine Freigabe.")
        return

    media_id = insta.publish_carousel(urls, caption)
    store.insert("posts", {"nummer": nummer, "topf": topf, "hook": post["hook"],
                           "caption": caption, "ig_media_id": media_id})
    telegram.send_album(dateien, f"✅ <b>Post #{nummer}</b> ist online\n„{telegram.esc(post['hook'])}“")
    print("Veröffentlicht:", media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        telegram.send(f"🚨 <b>Täglicher Post fehlgeschlagen</b>\n{telegram.esc(str(e))[:900]}")
        sys.exit(1)
