"""Schlanker Zugriff auf die Claude-API (Messages-Endpunkt)."""
import json
import re
import time

import requests

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def ask(system, user, max_tokens=1500):
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
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120,
        )
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(15 * (versuch + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Claude-API {r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    raise RuntimeError("Claude-API dauerhaft überlastet")


def ask_json(system, user, **kw):
    text = ask(system, user, **kw)
    text = text.replace("```json", "").replace("```", "")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Keine JSON-Antwort: " + text[:200])
    return json.loads(m.group(0))
