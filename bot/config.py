"""Zentrale Einstellungen für @senf.dazu. Zugänge kommen aus GitHub-Secrets."""
import os
from zoneinfo import ZoneInfo


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


# Zugänge
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5")
IG_TOKEN_SECRET = env("IG_ACCESS_TOKEN")
GRAPH = "https://graph.instagram.com/" + env("GRAPH_VERSION", "v24.0")
SUPABASE_URL = env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = env("SUPABASE_KEY")
TG_TOKEN = env("TELEGRAM_BOT_TOKEN")
TG_CHAT = env("TELEGRAM_CHAT_ID")

# Betrieb
BERLIN = ZoneInfo("Europe/Berlin")
POST_HOUR = 18            # frühestens ab 18:00 Uhr deutscher Zeit posten
BUCKET = "slides"
HANDLE = "@senf.dazu"
MAX_DRAFTS_PER_RUN = 15   # Kommentar-Entwürfe pro Stunde, damit Telegram nicht überläuft

# Themen-Töpfe – der Bot nimmt immer den, der am längsten nicht dran war
TOEPFE = [
    "Essen und Kochen",
    "Getränke, Kaffee und Kneipe",
    "Alltag und Gewohnheiten",
    "Wohnen und Haushalt",
    "Büro und Arbeitsalltag",
    "Urlaub, Reisen und Freizeit",
    "Feiertage, Feste und Traditionen",
    "Sprache, Dialekte und Redewendungen",
    "Einkaufen und Supermarkt",
    "Auto, Bahn und Unterwegssein",
]

# Diese Themen fasst der Bot nie an
TABU = [
    "Politik, Parteien, Wahlen, Migration, Krieg",
    "Religion und Weltanschauung",
    "Gesundheit, Ernährungs- und Diättipps, Medizin, Psyche",
    "Geld-, Anlage-, Steuer- und Rechtstipps",
    "echte, namentlich genannte Personen",
    "Marken oder Unternehmen schlechtmachen",
    "Menschengruppen (Herkunft, Geschlecht, Alter, Aussehen, Behinderung, Sexualität, Beruf)",
    "Sex, Drogen, Gewalt, Tod, Tragödien",
    "Kinder und Erziehung",
    "Tierwohl und Tierquälerei",
]
