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

# Les super-pouvoirs lourds restent chargeables, mais ne doivent pas ralentir
# le boot du serveur. Les imports OpenCV/ML se font à la première utilisation.
AUDIO_AVAILABLE = True
CAMERAS_AVAILABLE = True


def get_processor(*args, **kwargs):
    from PHOEBUS.audio_optimization import get_processor as _get_processor
    return _get_processor(*args, **kwargs)


def check_hallucination(*args, **kwargs):
    from PHOEBUS.audio_optimization import check_hallucination as _check_hallucination
    return _check_hallucination(*args, **kwargs)


def discover_cameras(*args, **kwargs):
    from PHOEBUS.network_cameras import discover_cameras as _discover_cameras
    return _discover_cameras(*args, **kwargs)


def get_camera_manager(*args, **kwargs):
    from PHOEBUS.network_cameras import get_camera_manager as _get_camera_manager
    return _get_camera_manager(*args, **kwargs)
