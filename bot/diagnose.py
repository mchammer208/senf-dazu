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

zeile("Ergebnis")
if a and b:
    print("Supabase antwortet auf beiden Wegen. Das Lesen ist nicht das Problem.")
elif b and not a:
    print("FUND: Ohne Authorization-Header liefert Supabase nichts zurück.")
    print("Genau diesen Weg nutzt der Bot gerade – das erklärt die leeren Ergebnisse.")
elif not a and not b:
    print("Supabase liefert auf keinem Weg Daten. Schlüssel oder Rechte prüfen.")
