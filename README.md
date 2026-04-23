# J.A.R.V.I.S

Assistant vocal local avec interface web Three.js, interface mobile, Home Assistant,
Google APIs, recherche web, vision ecran et fallback LLM.

## Installation portable

```bash
python3 scripts/bootstrap.py
```

Sur Windows:

```bat
py scripts\bootstrap.py
```

Le bootstrap cree `.venv`, installe les dependances Python, installe le frontend
avec npm, puis conserve les secrets dans `.env`.

## Configuration

1. Copiez `.env.example` vers `.env` si le bootstrap ne l'a pas deja fait.
2. Renseignez les cles utiles: Gemini, Home Assistant, YouTube, SerpAPI, Groq/xAI.
3. Pour Google Docs/Gmail/Calendar, placez `credentials.json` a la racine.

## Lancement

```bash
.venv/bin/python main2.py
```

Ou:

```bash
./demarrer_jarvis.sh
```

Sur Windows, utilisez `DÉMARRER_JARVIS.bat`.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose.py
```

PyAudio est optionnel. S'il ne s'installe pas, le micro PC et les applaudissements
sont desactives, mais le backend et l'interface mobile restent utilisables.
