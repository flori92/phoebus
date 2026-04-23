# jarvis/security.py
"""Sécurité JARVIS — audit, authentification WS, confirmations vocales."""
import json
from datetime import datetime

from jarvis.config import AUDIT_FILE, DEVICE_CONFIG_FILE
from jarvis.utils import normalize_text

# ── Actions sensibles ──────────────────────────────────────────────────────
# Trois niveaux de risque :
#  - "low"    : on exécute silencieusement.
#  - "medium" : on exécute, mais Jarvis annonce "J'applique X" avant de le faire
#               pour laisser 2 s à l'utilisateur pour couper à la voix (barge-in).
#  - "high"   : confirmation vocale explicite requise (dire "je confirme"
#               ou "annule").
DEFAULT_RISK_BY_ACTION = {
    # High : irréversible, destructif, appels sortants, écriture écran.
    "ha_alarme": "high",
    "whatsapp_appel": "high",
    "vision_ecrire": "high",
    "voir_ecran": "high",
    "agent_natif": "high",
    "renommer_fichier": "high",
    "deplacer_fichier": "high",
    # Medium : ça remue, c'est rattrapable.
    "ha_thermostat": "medium",
    "ha_scene": "medium",
    "trier_par_type": "medium",
    "trier_par_date": "medium",
    "trier_complet": "medium",
    "create_doc": "medium",
    "write_doc": "medium",
    "create_sheet": "medium",
    "creer_dossier": "medium",
    "oublier": "medium",
}

# Conservé pour compat descendante — dérivé du dict ci-dessus.
DEFAULT_SENSITIVE_ACTIONS = {a for a, lvl in DEFAULT_RISK_BY_ACTION.items() if lvl == "high"}

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


def risk_level_for(action):
    """Renvoie "low" | "medium" | "high" — résout aussi via le registre de skills."""
    # 1. device_config (override utilisateur)
    configured = DEVICE_CONFIG.get("risk_levels", {}) or {}
    if action in configured:
        lvl = str(configured[action]).lower()
        if lvl in ("low", "medium", "high"):
            return lvl

    # 2. override booléen historique "sensitive_actions"
    configured_bool = DEVICE_CONFIG.get("sensitive_actions", {})
    if action in configured_bool:
        return "high" if configured_bool[action] else "low"

    # 3. skill registry (chargé à la volée pour éviter l'import circulaire)
    try:
        from jarvis.skills import risk_of
        risk = risk_of(action, fallback=None)
        if risk in ("low", "medium", "high"):
            return risk
    except Exception:
        pass

    # 4. défauts internes
    return DEFAULT_RISK_BY_ACTION.get(action, "low")


def is_confirmation_text(text):
    text_norm = normalize_text(text)
    return any(word in text_norm for word in CONFIRM_WORDS)


def is_cancellation_text(text):
    text_norm = normalize_text(text)
    return any(word in text_norm for word in CANCEL_WORDS)
