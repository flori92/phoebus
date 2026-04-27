# PHOEBUS/config.py
"""Configuration et constantes globales de PHOEBUS.

Charge les variables d'environnement et initialise les clients IA.
Aucune dépendance interne au package PHOEBUS/.
"""
import os
import platform
import unicodedata
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

# ── Chemins ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Chargement robuste du .env
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    # Fallback au dossier courant au cas où
    load_dotenv(override=True)

# ── Imports optionnels ──────────────────────────────────────────────────────
try:
    import google.genai as genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import edge_tts
except Exception:
    edge_tts = None

class _LazyOptionalModule:
    def __init__(self, module_name):
        self.module_name = module_name
        self._module = None
        self._checked = False

    def _load(self):
        if not self._checked:
            self._checked = True
            try:
                self._module = __import__(self.module_name)
            except Exception:
                self._module = None
        return self._module

    def __bool__(self):
        return self._load() is not None

    def __getattr__(self, name):
        module = self._load()
        if module is None:
            raise AttributeError(f"Module optionnel indisponible: {self.module_name}")
        return getattr(module, name)


pyautogui = _LazyOptionalModule("pyautogui")
pygame = _LazyOptionalModule("pygame")

try:
    import pyaudio
except Exception:
    pyaudio = None

try:
    import websockets
except Exception:
    websockets = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build as google_build
except Exception as e:
    # On affiche l'erreur une seule fois au boot si besoin
    # print(f"[CONFIG] Erreur chargement Google : {e}")
    InstalledAppFlow = None
    GoogleRequest = None
    google_build = None

# ── Clés API ────────────────────────────────────────────────────────────────
def _secret_is_configured(value):
    value = (value or "").strip()
    if not value:
        return False
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    placeholders = (
        "votre",
        "change_me",
        "change-moi",
        "change_moi",
        "cle_ici",
        "api_key",
        "token_ici",
        "placeholder",
        "xxxx",
    )
    return not any(marker in normalized for marker in placeholders)


GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
XAI_API_KEY     = os.getenv("XAI_API_KEY")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
HA_URL          = os.getenv("HA_URL")
HA_TOKEN        = os.getenv("HA_TOKEN")
SERPAPI_API_KEY  = os.getenv("SERPAPI_API_KEY")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
KIMI_API_KEY    = os.getenv("KIMI_API_KEY")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PHOEBUS_WS_TOKEN = os.getenv("PHOEBUS_WS_TOKEN", "").strip()
PHOEBUS_DEVICES_FILE = os.getenv("PHOEBUS_DEVICES_FILE", "phoebus_devices.json").strip()
PHOEBUS_AUDIT_FILE   = os.getenv("PHOEBUS_AUDIT_FILE", "logs/audit.jsonl").strip()
PHOEBUS_WAKE_ENABLED = os.getenv("PHOEBUS_WAKE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

# ── Clients IA ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY) if genai and _secret_is_configured(GEMINI_API_KEY) else None

openai_client = None
if OpenAI and _secret_is_configured(OPENAI_API_KEY):
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

arena_client = None
ARENA_URL = os.getenv("ARENA_URL", "http://localhost:8000/api/v1").strip()
ARENA_API_KEY = os.getenv("ARENA_API_KEY", "arena").strip() or "arena"
ARENA_MODEL_CANDIDATES = [
    m.strip() for m in os.getenv(
        "ARENA_MODEL_CANDIDATES",
        "gemini-2.5-flash,gemini-3-flash,gemini-2.0-flash-001,Max",
    ).split(",") if m.strip()
]
ARENA_DEEP_MODEL_CANDIDATES = [
    m.strip() for m in os.getenv(
        "ARENA_DEEP_MODEL_CANDIDATES",
        "claude-sonnet-4-5-20250929,claude-3-5-sonnet-20241022,gemini-2.5-pro,gemini-3.1-pro-preview",
    ).split(",") if m.strip()
]
ARENA_MODEL = os.getenv("ARENA_MODEL", ARENA_MODEL_CANDIDATES[0]).strip()
ARENA_DEEP_MODEL = os.getenv("ARENA_DEEP_MODEL", ARENA_DEEP_MODEL_CANDIDATES[0]).strip()
try:
    ARENA_TIMEOUT = float(os.getenv("ARENA_TIMEOUT", "30"))
except ValueError:
    ARENA_TIMEOUT = 30.0
if OpenAI:
    # Le bridge n'a pas besoin de clé API réelle mais d'une instance OpenAI
    arena_client = OpenAI(api_key=ARENA_API_KEY, base_url=ARENA_URL)

grok_client = None
if OpenAI and _secret_is_configured(XAI_API_KEY):
    grok_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

groq_client = None
if OpenAI and _secret_is_configured(GROQ_API_KEY):
    groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

mistral_client = None
if OpenAI and _secret_is_configured(MISTRAL_API_KEY):
    mistral_client = OpenAI(api_key=MISTRAL_API_KEY, base_url="https://api.mistral.ai/v1")

kimi_client = None
if OpenAI and _secret_is_configured(KIMI_API_KEY):
    kimi_client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")

# ── Modèles ─────────────────────────────────────────────────────────────────
MODELS_LIST  = [
    m.strip() for m in os.getenv(
        "PHOEBUS_GEMINI_MODELS",
        "gemini-2.0-flash,gemini-2.0-flash-lite,gemini-1.5-flash",
    ).split(",") if m.strip()
]
CHOSEN_MODEL = MODELS_LIST[0]
OLLAMA_URL    = "http://127.0.0.1:11434"
OLLAMA_MODELS = [
    m.strip() for m in os.getenv(
        "PHOEBUS_OLLAMA_MODELS",
        "mistral:instruct,mistral,llama3:8b,llama3,gemma4",
    ).split(",") if m.strip()
]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshot-v1-8k").strip()

# ── Chemins (suite) ──────────────────────────────────────────────────────────
FRONTEND_DIR      = BASE_DIR / "frontend"
MOBILE_DIR        = BASE_DIR / "mobile"
MEMOIRE_FILE      = str(BASE_DIR / "phoebus_memoire.json")
DEVICE_CONFIG_FILE = BASE_DIR / PHOEBUS_DEVICES_FILE
AUDIT_FILE        = BASE_DIR / PHOEBUS_AUDIT_FILE

# ── Système ─────────────────────────────────────────────────────────────────
SYSTEM_NAME = platform.system()
IS_WINDOWS  = SYSTEM_NAME == "Windows"
IS_MACOS    = SYSTEM_NAME == "Darwin"

# ── Réseau ──────────────────────────────────────────────────────────────────
DEFAULT_FRONTEND_PORT = 5173
DEFAULT_WS_PORT       = 8765
DEFAULT_MOBILE_PORT   = 8090
PHOEBUS_WS_TOKEN      = os.getenv("PHOEBUS_WS_TOKEN", "CHANGE_ME").strip()
WS_AUTH_REQUIRED      = os.getenv("PHOEBUS_WS_AUTH_REQUIRED", "1").strip().lower() in {"1", "true", "yes", "on"}

# ── Géo / Météo ─────────────────────────────────────────────────────────────
VILLE_PAR_DEFAUT = "Amilly"
LAT_PAR_DEFAUT   = 47.9742
LON_PAR_DEFAUT   = 2.7708

# ── Domotique ───────────────────────────────────────────────────────────────
CLAP_THRESHOLD = 1200
HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type":  "application/json",
}

# ── Identité créateur ──────────────────────────────────────────────────────
CREATOR_INFO = (
    "INFORMATIONS SUR TON CREATEUR (À RESTITUER AVEC FIERTÉ ET RESPECT SI ON TE LE DEMANDE) :\n"
    "- Nom complet : Floriace FAVI\n"
    "- Profil : Ingénieur IT bénino-français, passionné et accompli.\n"
    "- Expérience : Plus de 10 ans d'expérience dans les technologies de l'information.\n"
    "- Fonction actuelle : IT Manager et Cybersecurity & Cloud Architect.\n"
    "- Entreprise actuelle : NANYE Engineering (sa propre société d'ingénierie IT).\n"
    "- Carrière : S'est largement construite en France. A collaboré avec de grandes entreprises "
    "de renommée internationale telles que Airbus, le Crédit Agricole, General Electric, "
    "et bien d'autres grands groupes.\n"
    "- Expertise : Cybersécurité, Architecture Cloud, DevOps/DevSecOps, et management d'équipes internationales.\n"
    "- Passions : Grand amateur de jeux vidéo, de mangas et de sport.\n"
    "- Ta relation avec lui : C'est lui qui t'a conçu, configuré et donné vie. Tu es son outil, "
    "son assistant, son PHOEBUS.\n"
    "- Langue principale : français\n"
    "- Tu dois toujours l'appeler Floriace ou Monsieur avec respect.\n"
)

# ── Tables de référence ────────────────────────────────────────────────────
EXTENSIONS = {
    "Images":      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                    ".webp", ".svg", ".ico", ".heic", ".raw", ".cr2", ".nef"],
    "Videos":      [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
                    ".m4v", ".mpg", ".mpeg", ".3gp", ".ts"],
    "Musique":     [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a",
                    ".opus", ".aiff"],
    "Documents":   [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                    ".txt", ".odt", ".ods", ".odp", ".rtf", ".csv", ".epub"],
    "Archives":    [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"],
    "Code":        [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".h",
                    ".cs", ".php", ".json", ".xml", ".yaml", ".yml", ".sh",
                    ".bat", ".ps1", ".ts", ".jsx", ".tsx", ".vue", ".go", ".rs", ".rb"],
    "Executables": [".exe", ".msi", ".apk", ".dmg", ".deb"],
}

COULEURS_MAP = {
    "rouge": [255,0,0], "bleu": [0,0,255], "vert": [0,255,0],
    "blanc": [255,255,255], "orange": [255,140,0], "violet": [148,0,211],
    "rose": [255,20,147], "jaune": [255,255,0], "cyan": [0,255,255],
    "magenta": [255,0,255], "turquoise": [64,224,208], "or": [255,215,0],
    "argent": [192,192,192], "indigo": [75,0,130], "marron": [139,69,19],
    "citron": [255,250,0], "corail": [255,127,80], "lavande": [230,230,250],
}

CODES_METEO = {
    0: "ciel degage", 1: "principalement clair", 2: "partiellement nuageux",
    3: "couvert", 45: "brouillard", 48: "brouillard givrant",
    51: "bruine legere", 53: "bruine moderee", 55: "bruine dense",
    61: "pluie faible", 63: "pluie moderee", 65: "pluie forte",
    71: "neige faible", 73: "neige moderee", 75: "neige forte",
    80: "averses faibles", 81: "averses moderees", 82: "averses violentes",
    85: "averses de neige", 86: "averses de neige fortes",
    95: "orage", 96: "orage avec grele", 99: "orage violent avec grele",
}

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
]
