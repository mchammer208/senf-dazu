"""Instagram-API (Instagram Login): Posten, Kommentare, Token-Erneuerung."""
import time
from datetime import datetime, timedelta, timezone

import requests

import store
from config import GRAPH, IG_TOKEN_SECRET


def token():
    """Aktueller Token liegt in Supabase (wird dort automatisch erneuert).
    Ein neuer Wert im GitHub-Secret gewinnt immer – so kannst du jederzeit neu setzen."""
    saat = store.get_setting("ig_token_seed")
    if IG_TOKEN_SECRET and (not saat or saat["value"] != IG_TOKEN_SECRET):
        store.set_setting("ig_token", IG_TOKEN_SECRET)
        store.set_setting("ig_token_seed", IG_TOKEN_SECRET)
        return IG_TOKEN_SECRET
    s = store.get_setting("ig_token")
    if not s:
        raise RuntimeError("Kein Instagram-Token – Secret IG_ACCESS_TOKEN fehlt.")
    return s["value"]


def _req(method, path, **params):
    params["access_token"] = token()
    url = f"{GRAPH}/{path}"
    if method == "POST":
        r = requests.post(url, data=params, timeout=60)
    else:
        r = requests.get(url, params=params, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram {method} {path}: {r.status_code} {r.text[:300]}")
    return r.json()


def me():
    return _req("GET", "me", fields="user_id,username")


def refresh_if_needed(tage=7):
    """Long-lived Tokens halten 60 Tage – wir erneuern wöchentlich."""
    token()  # stellt sicher, dass ein Token in Supabase liegt
    s = store.get_setting("ig_token")
    alt = datetime.fromisoformat(s["updated_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - alt < timedelta(days=tage):
        return False
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=30,
                     params={"grant_type": "ig_refresh_token", "access_token": s["value"]})
    if r.status_code >= 400:
        raise RuntimeError(f"Token-Erneuerung fehlgeschlagen: {r.status_code} {r.text[:300]}")
    store.set_setting("ig_token", r.json()["access_token"])
    return True


def _warten(container_id, versuche=36):
    for _ in range(versuche):
        status = _req("GET", container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container_id}: {status}")
        time.sleep(5)
    raise RuntimeError(f"Container {container_id} hängt nach 3 Minuten noch")


def publish_carousel(image_urls, caption):
    uid = me()["user_id"]
    kinder = [_req("POST", f"{uid}/media", image_url=u, is_carousel_item="true")["id"] for u in image_urls]
    for k in kinder:
        _warten(k)
    karussell = _req("POST", f"{uid}/media", media_type="CAROUSEL",
                     children=",".join(kinder), caption=caption)["id"]
    _warten(karussell)
    return _req("POST", f"{uid}/media_publish", creation_id=karussell)["id"]


def recent_media(limit=10):
    uid = me()["user_id"]
    return _req("GET", f"{uid}/media", fields="id,caption,timestamp", limit=limit).get("data", [])


def comments(media_id):
    return _req("GET", f"{media_id}/comments", fields="id,text,username,timestamp", limit=50).get("data", [])


def kommentieren(media_id, text):
    """Schreibt einen Kommentar unter einen eigenen Beitrag (POST /<media>/comments)."""
    return _req("POST", f"{media_id}/comments", message=text)


def reply(comment_id, text):
    return _req("POST", f"{comment_id}/replies", message=text)
