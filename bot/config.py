"""Zentrale Einstellungen für den Senf-Bot. Zugänge kommen aus GitHub-Secrets."""
import os
from zoneinfo import ZoneInfo


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


# Zugänge
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5-5")
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
HANDLE = env("ACCOUNT_HANDLE", "@gib.senf.dazu")  # nur Fallback – im Betrieb kommt der Name live von Instagram
MAX_DRAFTS_PER_RUN = 15   # Kommentar-Entwürfe pro Stunde, damit Telegram nicht überläuft

# Freigabe-Modus: "1" = Posts kommen erst als Entwurf nach Telegram und warten auf dich,
# "0" = der Bot postet selbstständig. Umschaltbar in GitHub unter
# Settings -> Secrets and variables -> Actions -> Variables -> POST_FREIGABE
POST_FREIGABE = env("POST_FREIGABE", "1") != "0"

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
    "Höflichkeit und Etikette",
    "Feiern und Einladungen",
    "Handy und Erreichbarkeit",
    "Nachbarschaft und Treppenhaus",
    "Kleidung im Alltag",
]

# Diese Themen fasst der Bot nie an
# Die vier Mechanismen, die in Kommentarspalten zünden. Pro Post wird einer gezogen.
# Die Beispiele sind Maß für die Tonlage, keine Vorlage zum Abschreiben.
HEBEL = {
    "Vorwurf": """Formuliere eine Regel, die den Leser schuldig spricht. „Wer X macht, …“ –
und dann steht da, was das über seine Rücksicht, sein Benehmen oder seinen Geschmack sagt.
Beispiele für die Tonlage:
- Wer sein Paket beim Nachbarn abgeben lässt, verteilt seine Arbeit um.
- Wer im Zug telefoniert, hält sein Gespräch für wichtiger als deine Ruhe.
- Wer zum Geburtstag Geld schenkt, hat sich nicht eine Minute Gedanken gemacht.""",

    "Heilige Kuh": """Schlachte etwas, an dem Leute hängen – ein Ritual, einen Brauch, eine
liebgewonnene Gemütlichkeit. Nüchtern benennen, was es in Wahrheit ist.
Beispiele für die Tonlage:
- Der Weihnachtsmarkt ist ein Stehcafé im Regen mit Zuschlag.
- Der Sonntagsspaziergang ist Langeweile mit Jacke.
- Selbstgebackener Kuchen ist meistens schlechter Kuchen.""",

    "Heuchelei": """Entlarve ein Ritual als kollektive Lüge: alle machen mit, keiner mag es,
niemand sagt es. So muss jeder widersprechen, um sich selbst freizusprechen.
Beispiele für die Tonlage:
- Niemand mag Sekt. Alle trinken ihn nur, weil Anstoßen ohne Glas komisch aussieht.
- Keiner liest die Bücher, die im Regal stehen.
- Grillabende macht niemand gern, Absagen wäre nur unhöflich.""",

    "Parteinahme": """Stell dich laut auf eine Seite eines Alltagsstreits, der längst zwei
Lager hat. Keine Abwägung, kein Sowohl-als-auch – ein Urteil.
Beispiele für die Tonlage:
- Im Flugzeug darf jeder die Lehne zurückstellen. Wer sich beschwert, hat das falsche Ticket gekauft.
- An der Kasse gehört der Wagen dicht an den Vordermann.
- Das Treppenhaus putzt der, der es dreckig macht, nicht der Plan an der Wand.""",
}

TABU = [
    "Politik, Parteien, Wahlen, Migration, Krieg",
    "Religion und Weltanschauung",
    "Gesundheit, Ernährungs- und Diättipps, Medizin, Psyche",
    "Geld-, Anlage-, Steuer- und Rechtstipps",
    "echte, namentlich genannte Personen",
    "Marken oder Unternehmen schlechtmachen",
    "Menschen abwerten für das, was sie sind – Herkunft, Geschlecht, Alter, Aussehen, "
    "Behinderung, Sexualität, Beruf, Einkommen (Urteile über freiwillige Gewohnheiten sind erlaubt)",
    "Sex, Drogen, Gewalt, Tod, Tragödien",
    "Kinder und Erziehung",
    "Tierwohl und Tierquälerei",
]
