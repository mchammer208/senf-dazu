"""Supabase: Tabellen (REST) und Bildablage (Storage)."""
from datetime import datetime, timezone

import requests

from config import BUCKET, SUPABASE_KEY, SUPABASE_URL


def _h(extra=None):
    h = {"apikey": SUPABASE_KEY}
    if not SUPABASE_KEY.startswith("sb_"):  # alter service_role-Key (JWT)
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    h.update(extra or {})
    return h


def _check(r, was):
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase {was}: {r.status_code} {r.text[:300]}")
    return r


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select(table, query=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{query}", headers=_h(), timeout=30)
    return _check(r, f"select {table}").json()


def insert(table, row):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", json=row, timeout=30,
                      headers=_h({"Content-Type": "application/json", "Prefer": "return=representation"}))
    return _check(r, f"insert {table}").json()[0]


def insert_ignore(table, row):
    """Legt eine Zeile ab und schweigt, wenn sie schon da ist (gleicher Schlüssel)."""
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", json=row, timeout=30,
                      headers=_h({"Content-Type": "application/json",
                                  "Prefer": "resolution=ignore-duplicates,return=minimal"}))
    _check(r, f"insert {table}")


def delete(table, query):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?{query}", headers=_h(), timeout=30)
    _check(r, f"delete {table}")


def update(table, match, values):
    q = "&".join(f"{k}=eq.{v}" for k, v in match.items())
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{q}", json=values, timeout=30,
                       headers=_h({"Content-Type": "application/json"}))
    _check(r, f"update {table}")


def get_setting(key):
    rows = select("settings", f"key=eq.{key}&select=value,updated_at")
    return rows[0] if rows else None


def set_setting(key, value):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/settings", timeout=30,
                      json={"key": key, "value": str(value), "updated_at": now_iso()},
                      headers=_h({"Content-Type": "application/json",
                                  "Prefer": "resolution=merge-duplicates"}))
    _check(r, "settings")


def upload(local_path, remote_path):
    with open(local_path, "rb") as f:
        r = requests.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{remote_path}", data=f.read(),
                          headers=_h({"Content-Type": "image/jpeg", "x-upsert": "true"}), timeout=60)
    _check(r, "upload")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{remote_path}"
