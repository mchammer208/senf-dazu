"""Diagnose: prüft jede Verbindung einzeln und zeigt die Rohantworten.

Schreibt nichts und postet nichts – reines Nachsehen.
"""
import os

import requests

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_KEY = (os.environ.get("SUPABASE_KEY") or "").strip()
IG_TOKEN = (os.environ.get("IG_ACCESS_TOKEN") or "").strip()


def zeile(titel):
    print(f"\n===== {titel} =====")


zeile("Zugänge")
print(f"SUPABASE_URL  : {SUPABASE_URL or 'FEHLT'}")
print(f"SUPABASE_KEY  : {SUPABASE_KEY[:12] + '…' if SUPABASE_KEY else 'FEHLT'} "
      f"(Länge {len(SUPABASE_KEY)}, Typ: "
      f"{'neuer Secret Key' if SUPABASE_KEY.startswith('sb_secret_') else 'publishable/anon – FALSCH!' if SUPABASE_KEY.startswith('sb_publishable_') else 'JWT (service_role?)' if SUPABASE_KEY.startswith('eyJ') else 'unbekannt'})")
print(f"IG_ACCESS_TOKEN: {'vorhanden, Länge ' + str(len(IG_TOKEN)) if IG_TOKEN else 'FEHLT'}")


def test_select(beschreibung, headers):
    url = f"{SUPABASE_URL}/rest/v1/post_drafts?status=eq.pending&order=id.desc&limit=20"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        inhalt = r.text[:400]
        anzahl = len(r.json()) if r.ok and isinstance(r.json(), list) else "—"
        print(f"{beschreibung}: HTTP {r.status_code}, {anzahl} Datensatz/Datensätze")
        print(f"   Antwort: {inhalt}")
        return r.ok and isinstance(r.json(), list) and len(r.json()) > 0
    except Exception as e:
        print(f"{beschreibung}: Fehler {e!r}")
        return False


zeile("Supabase – wartende Entwürfe")
nur_apikey = {"apikey": SUPABASE_KEY}
mit_auth = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
a = test_select("Nur apikey      ", nur_apikey)
b = test_select("apikey + Bearer ", mit_auth)

zeile("Supabase – alle Entwürfe (ohne Filter)")
try:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/post_drafts?select=id,nummer,status",
                     headers=mit_auth, timeout=30)
    print(f"HTTP {r.status_code}: {r.text[:400]}")
except Exception as e:
    print("Fehler:", repr(e))

zeile("Instagram")
try:
    r = requests.get("https://graph.instagram.com/v24.0/me",
                     params={"fields": "user_id,username", "access_token": IG_TOKEN}, timeout=30)
    print(f"HTTP {r.status_code}: {r.text[:300]}")
except Exception as e:
    print("Fehler:", repr(e))

GRAPH = "https://graph.instagram.com/v24.0"


def ig(pfad, **params):
    params["access_token"] = IG_TOKEN
    r = requests.get(f"{GRAPH}/{pfad}", params=params, timeout=30)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


zeile("Instagram – letzte Beiträge")
beitraege = []
try:
    code, daten = ig("me/media", fields="id,caption,timestamp,comments_count,media_type", limit=10)
    print(f"HTTP {code}")
    for m in (daten.get("data") or []):
        beitraege.append(m["id"])
        print(f"  {m['id']}  {m.get('media_type')}  {m.get('timestamp')}  "
              f"Kommentare: {m.get('comments_count')}")
    if not beitraege:
        print(f"  keine Beiträge geliefert – Rohantwort: {str(daten)[:300]}")
except Exception as e:
    print("Fehler:", repr(e))

zeile("Instagram – Kommentare je Beitrag")
for mid in beitraege:
    try:
        code, daten = ig(f"{mid}/comments", fields="id,text,username,timestamp", limit=50)
        eintraege = daten.get("data") if isinstance(daten, dict) else None
        print(f"  {mid}: HTTP {code}, {len(eintraege) if eintraege is not None else '—'} Kommentar(e)")
        for c in (eintraege or []):
            print(f"     @{c.get('username')} ({c.get('timestamp')}): {str(c.get('text'))[:80]}")
        if eintraege is None:
            print(f"     Rohantwort: {str(daten)[:300]}")
    except Exception as e:
        print(f"  {mid}: Fehler {e!r}")

TG = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()

zeile("Telegram – Bot und Warteschlange")
if not TG:
    print("Kein TELEGRAM_BOT_TOKEN gesetzt.")
else:
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG}/getMe", timeout=20).json()
        print("getMe:", str(r.get("result"))[:200])
    except Exception as e:
        print("getMe Fehler:", repr(e))

    # Ein gesetzter Webhook saugt alle Updates ab – dann bekommt getUpdates nie etwas
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG}/getWebhookInfo", timeout=20).json()
        info = r.get("result", {})
        print(f"Webhook-URL: {info.get('url') or '(keiner – richtig so)'}")
        print(f"   ausstehende Updates: {info.get('pending_update_count')}")
        if info.get("last_error_message"):
            print(f"   letzter Fehler: {info.get('last_error_message')}")
    except Exception as e:
        print("getWebhookInfo Fehler:", repr(e))

    # Warteschlange ansehen, ohne sie zu bestätigen
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG}/getUpdates",
                         params={"offset": 0, "timeout": 0}, timeout=30).json()
        liste = r.get("result", [])
        print(f"getUpdates(0): ok={r.get('ok')}, {len(liste)} Update(s)")
        if not r.get("ok"):
            print("   Fehler:", str(r)[:300])
        for u in liste:
            art = "Klick " + str(u.get("callback_query", {}).get("data")) \
                  if "callback_query" in u else "Nachricht"
            print(f"   id {u.get('update_id')}: {art}")
    except Exception as e:
        print("getUpdates Fehler:", repr(e))

zeile("Ergebnis")
if a and b:
    print("Supabase antwortet auf beiden Wegen. Das Lesen ist nicht das Problem.")
elif b and not a:
    print("FUND: Ohne Authorization-Header liefert Supabase nichts zurück.")
    print("Genau diesen Weg nutzt der Bot gerade – das erklärt die leeren Ergebnisse.")
elif not a and not b:
    print("Keine wartenden Entwürfe gefunden. Das ist normal, wenn alles gepostet ist –")
    print("ein Fehler wäre es nur, wenn die Abfrage ohne Filter oben ebenfalls leer bliebe.")
