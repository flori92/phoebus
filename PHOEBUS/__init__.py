# PHOEBUS — Personal Holistic Omniscient Entity Bridging Universal Systems
# 
# Architecture modulaire avec 7 Super-Pouvoirs:
#   ✅ NEW: audio_optimization.py      → VAD robuste + AEC + hallucinations
#   ✅ NEW: network_cameras.py         → Caméras PC/réseau/téléphone
#   config.py                          → configuration, env, constantes
#   state.py                           → état global mutable, fonctions WS partagées
#   utils.py                           → utilitaires système
#   security.py                        → auth, audit, confirmations
#   memory.py                          → mémoire persistante JSON
#   home.py                            → Home Assistant, météo, sport
#   voice.py                           → TTS / STT / claps
#   vision.py                          → capture écran + analyse IA + caméras
#   desktop.py                         → fichiers, apps, YouTube, WhatsApp
#   ai.py                              → backends IA (Gemini, Grok, Groq, Ollama, Arena)
#   google_services.py                 → Google Docs, Gmail, Calendar, Sheets
#   actions.py                         → dispatcher JSON → handlers
#   server.py                          → WebSocket, HTTP mobile, boucle principale
#   multi_user.py                      → reconnaissance vocale multi-utilisateurs
#   brain_router.py                    → routeur IA intelligent (speed/smart/privacy)

__version__ = "2.0.0-superpouvoirs"
__author__ = "Floriace"
__title__ = "PHOEBUS — The Brilliant One"

# Initialiser les super-pouvoirs au boot
try:
    from PHOEBUS.audio_optimization import get_processor, check_hallucination
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

try:
    from PHOEBUS.network_cameras import discover_cameras, get_camera_manager
    CAMERAS_AVAILABLE = True
except ImportError:
    CAMERAS_AVAILABLE = False
