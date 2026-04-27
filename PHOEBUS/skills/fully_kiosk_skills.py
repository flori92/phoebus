import os
import requests
from PHOEBUS.skills.registry import skill

# On récupère les accès depuis le .env
FULLY_URL = os.getenv("FULLY_KIOSK_URL", "http://192.168.1.XX:2323")
FULLY_PASS = os.getenv("FULLY_KIOSK_PASSWORD", "")

def _fully_cmd(cmd, **kwargs):
    if not FULLY_URL or "XX" in FULLY_URL:
        return False, "URL Fully Kiosk non configurée dans le .env"
    
    url = f"{FULLY_URL}/?cmd={cmd}&password={FULLY_PASS}"
    for k, v in kwargs.items():
        url += f"&{k}={v}"
    
    try:
        r = requests.get(url, timeout=5)
        return r.status_code == 200, r.text
    except Exception as e:
        return False, str(e)

@skill(
    "fully_screen",
    risk="low",
    help_text="Allume ou éteint l'écran de la tablette Fully Kiosk",
    describe=lambda d: f"Mettre l'écran de la tablette en {d.get('state')}"
)
async def fully_screen(data: dict):
    state = data.get("state", "on").lower()
    cmd = "screenOn" if state == "on" else "screenOff"
    ok, _ = _fully_cmd(cmd)
    return f"Écran de la tablette {state}." if ok else "Échec du contrôle de la tablette."

@skill(
    "fully_load_url",
    risk="low",
    help_text="Charge une URL spécifique sur la tablette",
    describe=lambda d: f"Charger l'URL {d.get('url')} sur la tablette"
)
async def fully_load_url(data: dict):
    url_to_load = data.get("url")
    if not url_to_load: return "Quelle URL dois-je charger ?"
    ok, _ = _fully_cmd("loadURL", url=url_to_load)
    return "URL envoyée à la tablette." if ok else "Erreur de chargement."

@skill(
    "fully_say",
    risk="low",
    help_text="Fait parler la tablette via TTS",
    describe=lambda d: f"Faire dire à la tablette : {d.get('text')}"
)
async def fully_say(data: dict):
    text = data.get("text")
    if not text: return "Que doit dire la tablette ?"
    ok, _ = _fully_cmd("textToSpeech", text=text)
    return "Message envoyé à la tablette." if ok else "Échec du TTS tablette."
