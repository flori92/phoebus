# jarvis/config.py
"""Configuration et constantes globales de JARVIS.

Charge les variables d'environnement et initialise les clients IA.
Aucune dépendance interne au package jarvis/.
"""
import os
import platform
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

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

try:
    import pygame
except Exception:
    pygame = None

try:
    import pyautogui
except Exception:
    pyautogui = None

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
JARVIS_WS_TOKEN = os.getenv("JARVIS_WS_TOKEN", "").strip()
JARVIS_DEVICES_FILE = os.getenv("JARVIS_DEVICES_FILE", "jarvis_devices.json").strip()
JARVIS_AUDIT_FILE   = os.getenv("JARVIS_AUDIT_FILE", "logs/audit.jsonl").strip()

# ── Clients IA ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None

openai_client = None
if OpenAI and OPENAI_API_KEY and OPENAI_API_KEY not in ["VOTRE_CLE_ICI", "VOTRE_API"]:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

grok_client = None
if OpenAI and XAI_API_KEY and XAI_API_KEY not in ["VOTRE_CLE_ICI", "VOTRE_API"]:
    grok_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

groq_client = None
if OpenAI and GROQ_API_KEY and GROQ_API_KEY not in ["VOTRE_CLE_ICI", "VOTRE_API"]:
    groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

mistral_client = None
if OpenAI and MISTRAL_API_KEY and MISTRAL_API_KEY not in ["VOTRE_CLE_ICI", "VOTRE_API"]:
    mistral_client = OpenAI(api_key=MISTRAL_API_KEY, base_url="https://api.mistral.ai/v1")

kimi_client = None
if OpenAI and KIMI_API_KEY and KIMI_API_KEY not in ["VOTRE_CLE_ICI", "VOTRE_API"]:
    kimi_client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")

# ── Modèles ─────────────────────────────────────────────────────────────────
MODELS_LIST  = [
    m.strip() for m in os.getenv(
        "JARVIS_GEMINI_MODELS",
        "gemini-2.0-flash,gemini-2.0-flash-lite,gemini-1.5-flash",
    ).split(",") if m.strip()
]
CHOSEN_MODEL = MODELS_LIST[0]
OLLAMA_URL    = "http://127.0.0.1:11434"
OLLAMA_MODELS = [
    m.strip() for m in os.getenv(
        "JARVIS_OLLAMA_MODELS",
        "mistral:instruct,mistral,llama3:8b,llama3,gemma4",
    ).split(",") if m.strip()
]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshot-v1-8k").strip()

# ── Chemins ─────────────────────────────────────────────────────────────────
BASE_DIR          = Path(__file__).resolve().parent.parent
FRONTEND_DIR      = BASE_DIR / "frontend"
MOBILE_DIR        = BASE_DIR / "mobile"
MEMOIRE_FILE      = str(BASE_DIR / "jarvis_memoire.json")
DEVICE_CONFIG_FILE = BASE_DIR / JARVIS_DEVICES_FILE
AUDIT_FILE        = BASE_DIR / JARVIS_AUDIT_FILE

# ── Système ─────────────────────────────────────────────────────────────────
SYSTEM_NAME = platform.system()
IS_WINDOWS  = SYSTEM_NAME == "Windows"
IS_MACOS    = SYSTEM_NAME == "Darwin"

# ── Réseau ──────────────────────────────────────────────────────────────────
DEFAULT_FRONTEND_PORT = 5173
DEFAULT_WS_PORT       = 8765
DEFAULT_MOBILE_PORT   = 8080
WS_AUTH_REQUIRED = bool(JARVIS_WS_TOKEN and JARVIS_WS_TOKEN not in {"CHANGE_ME", "VOTRE_TOKEN_ICI"})

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
    "son assistant, son JARVIS.\n"
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
