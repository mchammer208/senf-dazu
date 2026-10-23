"""Schlanker Zugriff auf die Claude-API (Messages-Endpunkt)."""
import json
import re
import time

import requests

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


class ApiFehler(RuntimeError):
    """Dauerhafter Fehler der Claude-API – Wiederholen bringt nichts."""


def ask(system, user, max_tokens=2000):
    nachrichten = [{"role": "user", "content": user}]

    for versuch in range(4):
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": nachrichten,
            },
            timeout=120,
        )
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(15 * (versuch + 1))
            continue
        if r.status_code >= 400:
            raise ApiFehler(f"Claude-API {r.status_code}: {r.text[:300]}")
        daten = r.json()
        text = "".join(b.get("text", "") for b in daten["content"] if b.get("type") == "text")
        if daten.get("stop_reason") == "max_tokens":
            raise ValueError("Antwort wurde abgeschnitten (max_tokens zu klein)")
        return text
    raise RuntimeError("Claude-API dauerhaft überlastet")


def _bloecke(text):
    """Findet vollständige {...}-Blöcke über eine Klammerzählung (robuster als Regex)."""
    tiefe, start, in_string, escaped = 0, None, False, False
    for i, z in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif z == "\\":
                escaped = True
            elif z == '"':
                in_string = False
            continue
        if z == '"':
            in_string = True
        elif z == "{":
            if tiefe == 0:
                start = i
            tiefe += 1
        elif z == "}":
            if tiefe > 0:
                tiefe -= 1
                if tiefe == 0 and start is not None:
                    yield text[start:i + 1]


def ask_json(system, user, versuche=3, **kw):
    """Holt eine JSON-Antwort und gibt bei unsauberem Format nicht gleich auf."""
    letzter_fehler = ""
    frage = user
    for nr in range(versuche):
        try:
            text = ask(system, frage, **kw)
        except ValueError as e:          # abgeschnitten -> mit mehr Luft neu versuchen
            letzter_fehler = str(e)
            kw["max_tokens"] = int(kw.get("max_tokens", 2000) * 1.5)
            time.sleep(2)
            continue

        text = text.replace("```json", "").replace("```", "")
        for block in _bloecke(text):
            try:
                return json.loads(block)
            except json.JSONDecodeError as e:
                letzter_fehler = f"{e} in: {block[:160]}"

        if not letzter_fehler:
            letzter_fehler = "kein JSON-Block gefunden in: " + text[:160]
        frage = (user + "\n\nWICHTIG: Deine letzte Antwort war kein gültiges JSON "
                 f"({letzter_fehler[:120]}). Antworte ausschließlich mit einem JSON-Objekt, "
                 "ohne Einleitung, ohne Code-Block, ohne Kommentar.")
        time.sleep(2)

    raise ValueError(f"Nach {versuche} Versuchen kein gültiges JSON. Letzter Fehler: {letzter_fehler[:300]}")
