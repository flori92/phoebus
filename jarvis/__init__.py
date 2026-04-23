# jarvis/ — Package principal de J.A.R.V.I.S
#
# Architecture modulaire :
#   config.py          → configuration, env, constantes
#   state.py           → état global mutable, fonctions WS partagées
#   utils.py           → utilitaires système
#   security.py        → auth, audit, confirmations
#   memory.py          → mémoire persistante JSON
#   home.py            → Home Assistant, météo, sport
#   voice.py           → TTS / STT / claps
#   vision.py          → capture écran + analyse IA
#   desktop.py         → fichiers, apps, YouTube, WhatsApp
#   ai.py              → backends IA (Gemini, Grok, Groq, Ollama)
#   google_services.py → Google Docs, Gmail, Calendar, Sheets
#   actions.py         → dispatcher JSON → handlers
#   server.py          → WebSocket, HTTP mobile, boucle principale
