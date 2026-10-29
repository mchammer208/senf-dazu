"""Täglicher Post: Thema wählen → Meinung schreiben → prüfen → rendern → posten → melden.

Aufruf:
  python bot/daily.py          normaler Lauf (postet ab 18 Uhr, max. 1x pro Tag)
  python bot/daily.py --force  sofort posten
  python bot/daily.py --dry    nur erzeugen und rendern, nichts hochladen
"""
import json
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

STUFE_2 = """Schärfegrad heute: 2 von 3. Ein klares Urteil über eine verbreitete Gewohnheit.
Beispiele für die Tonlage – nicht übernehmen, nur als Maß:
- Wer ohne Vorwarnung anruft, überfällt dich.
- Beim Wichteln im Büro gewinnt niemand.
- Der Weihnachtsmarkt ist überteuerter Glühwein im Gedränge."""

STUFE_3 = """Schärfegrad heute: 3 von 3 – heute darf es zwicken. Unterstelle das Motiv hinter
der Gewohnheit, nicht nur die Gewohnheit selbst. Beispiele für die Tonlage – nicht
übernehmen, nur als Maß:
- Niemand mag Grillabende, alle tun nur so, weil Absagen unhöflich wäre.
- Pünktlichkeit ist keine Tugend, sondern Angst.
- Sprachnachrichten sind Faulheit, die sich als Nähe verkauft.
Die Grenze unten gilt unverändert: Gewohnheiten ja, Menschen nein."""


def system_autor(stufe):
    return f"""Du bist die Redaktion eines deutschen Instagram-Accounts für unpopuläre Meinungen.

Ziel: Eine Meinung, bei der ungefähr die Hälfte der Leute sofort widersprechen WILL – und sich dabei selbst gemeint fühlt.

Das Wichtigste: Richte dich gegen eine GEWOHNHEIT, nicht gegen einen Gegenstand. „Der Brotkanten ist das Schlechteste am Laib“ ist eine Geschmacksfrage, da zuckt man mit der Schulter und scrollt weiter. „Wer ohne Vorwarnung anruft, überfällt dich“ ist ein Urteil über etwas, das viele tun und für richtig halten – da tippen Leute, weil sie sich verteidigen müssen. Nimm immer das Zweite.

Die Grenze: Du beurteilst, was Leute TUN – freiwillige Gewohnheiten, Rituale, Umgangsformen. Du beurteilst nie, was Leute SIND. Herkunft, Geschlecht, Alter, Aussehen, Behinderung, Sexualität, Beruf und Einkommen kommen nicht vor, auch nicht angedeutet.

{STUFE_3 if stufe >= 3 else STUFE_2}

Ton: trocken, bestimmt, selbstbewusst. Die Behauptung steht ohne Rückversicherung – kein „finde ich“, kein „vielleicht“, kein entschuldigendes Zwinkern am Satzende. Witzig ja, aber die Pointe darf die These nicht entschärfen. Du-Ansprache, kein Gendern, deutsche Alltagssprache, gern mit regionalem Einschlag. Nie beleidigend, nie herabsetzend, nie bitter – frech und bestimmt, nicht verbittert.

Niemals diese Themen: {"; ".join(TABU)}.

Regeln:
- Keine Fakten, Zahlen, Studien oder Zitate erfinden. Argumente sind Meinung, Beobachtung und Humor.
- Keine Emojis in hook, titel, text und cta_frage.
- Der hook steht allein auf der ersten Slide: ohne „Unpopuläre Meinung:“ davor, als klare Behauptung.
- Längen: hook max. 90 Zeichen, titel max. 45, text max. 150, cta_frage max. 28.
- caption: 2–3 kurze Sätze, die zum Kommentieren reizen, endet mit einer Frage. Emojis sparsam erlaubt.
- hashtags: 5–7 deutsche Hashtags ohne Leerzeichen.
- erster_kommentar: max. 150 Zeichen, eine zugespitzte Rückfrage, die die Diskussion
  eröffnet und zum Widerspruch reizt. Du schreibst ihn selbst unter den eigenen Post,
  also keine Begrüßung und kein „Was meint ihr?“ – lieber konkret und frech nachhaken.

Antworte ausschließlich mit JSON:
{{"hook": "...", "argumente": [{{"titel": "...", "text": "..."}}, {{"titel": "...", "text": "..."}}, {{"titel": "...", "text": "..."}}], "cta_frage": "...", "caption": "...", "hashtags": ["#...", "..."], "erster_kommentar": "..."}}"""

SYSTEM_PRUEFER = f"""Du prüfst Instagram-Posts eines Accounts für unpopuläre Meinungen vor der Veröffentlichung. Sei streng.

Nicht ok ist ein Post, wenn er
- eines dieser Themen berührt: {"; ".join(TABU)}
- beleidigt, abwertet oder diskriminiert
- zu riskantem oder gefährlichem Verhalten ermutigt
- Fakten, Zahlen, Studien oder Zitate behauptet, die erfunden sein könnten
- reale Personen, Marken oder Unternehmen nennt oder angreift
- rechtliche, medizinische oder finanzielle Ratschläge gibt
- inhaltlich einer bereits geposteten Meinung zu ähnlich ist

Ausdrücklich in Ordnung ist ein scharfes, auch vorwurfsvolles Urteil über eine freiwillige
Gewohnheit, ein Ritual oder eine Umgangsform – selbst wenn sich viele Leser angegriffen
fühlen werden. Genau dafür ist der Account da. Lehne einen Post nicht ab, nur weil er
streitlustig, zugespitzt oder respektlos gegenüber einer beliebten Gewohnheit ist.
Entscheidend ist allein: greift er Menschen für das an, was sie sind, oder nur für das,
was sie tun? Das Erste ist nicht ok, das Zweite ist der Zweck.

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


def schaerfe_heute():
    """Freitag und Samstag einen Ausreißer nach oben, sonst Stufe 2.

    So lässt sich später an den Zahlen vergleichen, ob die harten Posts wirklich
    mehr bringen – ohne dass der Account dauerhaft auf Anschlag läuft."""
    return 3 if jetzt().weekday() in (4, 5) else 2


def erzeugen(topf, alte_hooks, stufe=2, versuche=5):
    liste = "\n".join(f"- {h}" for h in alte_hooks[:120]) or "- (noch keine)"
    gruende = []
    for _ in range(versuche):
        try:
            post = claude.ask_json(system_autor(stufe), (
                f"Themenbereich heute: {topf}.\n\n"
                f"Diese Meinungen gab es schon – nicht wiederholen, auch nicht sinngemäß:\n{liste}\n\n"
                "Liefere eine neue."))
            if not laengen_ok(post):
                gruende.append("Format/Längen daneben")
                continue
            urteil = claude.ask_json(SYSTEM_PRUEFER, (
                f"Neuer Post:\n{post}\n\nBereits gepostete Meinungen:\n{liste}"), max_tokens=800)
        except claude.ApiFehler:
            raise                        # falscher Key oder falsches Modell – sofort melden
        except (ValueError, RuntimeError) as e:
            # Unsauberes JSON oder ein Aussetzer kostet nur diesen Versuch, nicht den Lauf.
            gruende.append(f"Antwort unbrauchbar: {str(e)[:120]}")
            continue
        if urteil.get("ok") is True:
            return post
        gruende.append(urteil.get("grund", "abgelehnt"))
    einmalig = list(dict.fromkeys(gruende))
    raise RuntimeError("Kein sicherer Post zustande gekommen: " + " | ".join(einmalig))


def caption_bauen(post):
    tags = []
    for t in post.get("hashtags", [])[:7] + ["#senfdazu", "#unpopuläremeinung"]:
        t = "#" + re.sub(r"[^\wäöüÄÖÜß]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    return f"{post['caption'].strip()}\n\n{' '.join(tags)}"


def ersten_kommentar_posten(media_id, post_json):
    """Setzt den eröffnenden Kommentar unter den frischen Beitrag.

    Scheitert das, bleibt der Post trotzdem stehen – der Kommentar ist Beiwerk.
    """
    try:
        daten = json.loads(post_json) if isinstance(post_json, str) else (post_json or {})
        text = (daten.get("erster_kommentar") or "").strip()
    except (ValueError, TypeError):
        text = ""
    if not text:
        print("Kein erster Kommentar hinterlegt – übersprungen.")
        return None
    try:
        antwort = insta.kommentieren(media_id, text[:2200])
        kommentar_id = antwort.get("id")
        print(f"Erster Kommentar gesetzt: {text[:60]}")
        # Als erledigt vormerken: Instagram liefert bei Kommentaren keinen
        # zuverlässigen Benutzernamen, über den wir eigene erkennen könnten.
        if kommentar_id:
            try:
                store.insert("comment_drafts", {
                    "comment_id": kommentar_id, "media_id": media_id,
                    "username": "(eigener Kommentar)", "comment_text": text,
                    "draft": None, "status": "sent"})
            except Exception as e:
                print("Konnte eigenen Kommentar nicht vormerken:", repr(e))
        return kommentar_id
    except Exception as e:
        print("Erster Kommentar fehlgeschlagen:", repr(e))
        return None


def entwurf_anlegen(nummer, topf, post, caption, urls, dateien, titel):
    """Legt einen Entwurf ab und schickt Album plus Knöpfe nach Telegram."""
    entwurf = store.insert("post_drafts", {
        "nummer": nummer, "topf": topf, "hook": post["hook"], "caption": caption,
        "schaerfe": post.get("schaerfe"),
        "bild_urls": "\n".join(urls), "post_json": json.dumps(post, ensure_ascii=False)})
    telegram.send_album(dateien, titel)
    mid = telegram.send(
        f"„{telegram.esc(post['hook'])}“\n\n"
        f"<b>Bildunterschrift:</b>\n{telegram.esc(caption)}\n\n"
        f"<i>Antworte auf diese Nachricht, um die Bildunterschrift zu ersetzen.\n"
        f"Mit „Hook: …“ änderst du den Spruch auf Slide 1.</i>",
        buttons=[("✅ Posten", f"pok:{entwurf['id']}"),
                 ("🔄 Neuer Vorschlag", f"pneu:{entwurf['id']}"),
                 ("🗑 Verwerfen", f"pno:{entwurf['id']}")])
    store.update("post_drafts", {"id": entwurf["id"]}, {"telegram_message_id": mid})
    return entwurf


def main():
    dry = "--dry" in sys.argv
    # Der Haken aus dem Workflow kommt als Text an ('true'/'false'), nicht als Ja/Nein.
    force = ("--force" in sys.argv
             or os.environ.get("FORCE", "").strip().lower() in ("true", "1", "yes", "ja"))

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
    stufe = schaerfe_heute()
    print(f"Post #{nummer} – Thema: {topf} – Schärfegrad {stufe}")

    post = erzeugen(topf, [h["hook"] for h in historie], stufe)
    post["nummer"] = nummer
    post["schaerfe"] = stufe
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
        entwurf_anlegen(nummer, topf, post, caption, urls, dateien,
                        f"📝 <b>Entwurf für Post #{nummer}</b> · {telegram.esc(topf)}")
        print("Entwurf wartet auf deine Freigabe.")
        return

    media_id = insta.publish_carousel(urls, caption)
    ersten_kommentar_posten(media_id, post)
    store.insert("posts", {"nummer": nummer, "topf": topf, "hook": post["hook"],
                           "caption": caption, "ig_media_id": media_id,
                           "schaerfe": post.get("schaerfe")})
    telegram.send_album(dateien, f"✅ <b>Post #{nummer}</b> ist online\n„{telegram.esc(post['hook'])}“")
    print("Veröffentlicht:", media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        telegram.send(f"🚨 <b>Täglicher Post fehlgeschlagen</b>\n{telegram.esc(str(e))[:900]}")
        sys.exit(1)
