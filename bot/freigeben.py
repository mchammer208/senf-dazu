"""Notausgang: veröffentlicht den neuesten wartenden Entwurf direkt, ohne Telegram.

Aufruf:
  python bot/freigeben.py           neuesten wartenden Entwurf posten
  python bot/freigeben.py --liste   nur anzeigen, was wartet
"""
import os
import sys
import traceback

import insta
import store
import telegram


def wartende():
    return store.select("post_drafts", "status=eq.pending&order=id.desc&limit=20")


def nur_anzeigen():
    """Der Haken aus dem Workflow kommt als Text an ('true'/'false'), nicht als echtes
    Ja/Nein. Ein schlichtes 'wenn gesetzt' wäre bei 'false' fälschlich wahr."""
    if "--liste" in sys.argv:
        return True
    return os.environ.get("NUR_ANZEIGEN", "").strip().lower() in ("true", "1", "yes", "ja")


def main():
    modus = "NUR ANZEIGEN" if nur_anzeigen() else "POSTEN"
    print(f"Modus: {modus}")
    offen = wartende()
    if not offen:
        print("Kein wartender Entwurf vorhanden.")
        return

    print(f"{len(offen)} wartende(r) Entwurf/Entwürfe:")
    for e in offen:
        print(f"  #{e['nummer']} (id {e['id']}, {e['created_at']}): {e['hook']}")

    if nur_anzeigen():
        print("\nNichts gepostet – Haken „Nur anzeigen“ war gesetzt.")
        return

    entwurf = offen[0]
    urls = [u for u in entwurf["bild_urls"].split("\n") if u.strip()]
    print(f"\nVeröffentliche Entwurf id {entwurf['id']} mit {len(urls)} Bildern …")

    media_id = insta.publish_carousel(urls, entwurf["caption"])
    store.insert("posts", {"nummer": entwurf["nummer"], "topf": entwurf["topf"],
                           "hook": entwurf["hook"], "caption": entwurf["caption"],
                           "ig_media_id": media_id})
    store.update("post_drafts", {"id": entwurf["id"]}, {"status": "published"})

    # Alle älteren Entwürfe derselben Nummer aus dem Weg räumen
    for alt in offen[1:]:
        if alt["nummer"] == entwurf["nummer"]:
            store.update("post_drafts", {"id": alt["id"]}, {"status": "rejected"})

    print("Veröffentlicht:", media_id)
    telegram.send(f"✅ <b>Post #{entwurf['nummer']}</b> ist online\n„{telegram.esc(entwurf['hook'])}“")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        telegram.send(f"🚨 <b>Freigabe fehlgeschlagen</b>\n{telegram.esc(str(e))[:900]}")
        sys.exit(1)
