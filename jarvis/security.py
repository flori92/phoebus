# jarvis/security.py
"""Sécurité JARVIS — audit, authentification WS, confirmations vocales."""
import json
from datetime import datetime

from jarvis.config import AUDIT_FILE, DEVICE_CONFIG_FILE
from jarvis.utils import normalize_text

# ── Actions sensibles ──────────────────────────────────────────────────────
DEFAULT_SENSITIVE_ACTIONS = {
    "ha_alarme", "ha_thermostat", "ha_scene",
    "voir_ecran", "vision_ecrire", "whatsapp_appel",
    "trier_par_type", "trier_par_date", "trier_complet",
    "renommer_fichier", "deplacer_fichier",
    "create_doc", "write_doc", "create_sheet",
}

CONFIRM_WORDS = {
    "confirme", "je confirme", "ok confirme", "oui confirme",
    "valide", "vas y", "vas-y", "execute", "exécute",
}

CANCEL_WORDS = {
    "annule", "annuler", "stop", "laisse tomber", "oublie", "non",
}


# ── Config devices ─────────────────────────────────────────────────────────

def load_device_config():
    if not DEVICE_CONFIG_FILE.exists():
        return {"aliases": {}, "sensitive_actions": {}, "settings": {}}
    try:
        with open(DEVICE_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        print(f"[CONFIG] Impossible de lire {DEVICE_CONFIG_FILE.name} : {e}")
    return {"aliases": {}, "sensitive_actions": {}, "settings": {}}


DEVICE_CONFIG = load_device_config()


# ── Journal d'audit ────────────────────────────────────────────────────────

def audit_log(event, **details):
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **details,
        }
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[AUDIT] Erreur journalisation : {e}")


# ── Fonctions de sécurité ──────────────────────────────────────────────────

def sanitize_action_data(data):
    safe = {}
    for key, value in dict(data or {}).items():
        if key in {"token", "content", "audio_b64"}:
            safe[key] = "<redacted>"
        elif isinstance(value, str) and len(value) > 160:
            safe[key] = value[:157] + "..."
        else:
            safe[key] = value
    return safe


def describe_action(data):
    action = data.get("action", "")
    descriptions = {
        "ha_alarme":       lambda d: f"changer l'alarme en mode {d.get('etat', 'on')}",
        "ha_thermostat":   lambda d: f"regler le thermostat a {d.get('temperature', 20)} degres",
        "ha_scene":        lambda d: f"activer la scene {d.get('nom', 'inconnue')}",
        "voir_ecran":      lambda d: f"controler l'ecran pour {d.get('instruction', 'une action visuelle')}",
        "vision_ecrire":   lambda d: f"ecrire dans l'interface pour {d.get('instruction', 'une saisie')}",
        "whatsapp_appel":  lambda d: f"lancer un appel WhatsApp vers {d.get('contact', 'un contact')}",
        "renommer_fichier": lambda d: f"renommer {d.get('ancien', 'un fichier')} en {d.get('nouveau', 'nouveau nom')}",
        "deplacer_fichier": lambda d: f"deplacer {d.get('fichier', 'un fichier')} vers {d.get('destination', 'la destination')}",
        "trier_par_type":  lambda _: "trier les fichiers par type",
        "trier_par_date":  lambda _: "trier les fichiers par date",
        "trier_complet":   lambda _: "trier les fichiers par type puis par date",
        "create_doc":      lambda d: f"creer le document {d.get('title', 'Document JARVIS')}",
        "write_doc":       lambda _: "modifier le document Google en cours",
        "create_sheet":    lambda d: f"creer la feuille {d.get('title', 'Feuille JARVIS')}",
    }
    fn = descriptions.get(action)
    return fn(data) if fn else (action or "une action")


def is_sensitive_action(action):
    configured = DEVICE_CONFIG.get("sensitive_actions", {})
    if action in configured:
        return bool(configured[action])
    return action in DEFAULT_SENSITIVE_ACTIONS


def is_confirmation_text(text):
    text_norm = normalize_text(text)
    return any(word in text_norm for word in CONFIRM_WORDS)


def is_cancellation_text(text):
    text_norm = normalize_text(text)
    return any(word in text_norm for word in CANCEL_WORDS)
