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
avec npm, cree `.env` si besoin et prepare `jarvis_devices.json` a partir du modele.

## Configuration

1. Copiez `.env.example` vers `.env` si le bootstrap ne l'a pas deja fait.
2. Renseignez les cles utiles: Gemini, Home Assistant, YouTube, SerpAPI, Groq/xAI.
3. Definissez `JARVIS_WS_TOKEN` avec une valeur forte pour securiser les clients web/mobile.
4. Adaptez `jarvis_devices.json` aux entites de votre Home Assistant.
5. Pour Google Docs/Gmail/Calendar, placez `credentials.json` a la racine.

## Cerveau multi-provider

Jarvis route maintenant chaque requete vers le meilleur cerveau disponible:

- fast-path local pour les commandes evidentes (domotique, heure, date)
- Gemini pour les requetes complexes, la recherche outillee et la vision
- Groq pour les reponses texte tres rapides
- Mistral comme cerveau francophone/europeen secondaire
- Grok pour les sujets X/Twitter si `XAI_API_KEY` est configuree
- Kimi (Moonshot AI) comme modele chinois alternatif puissant
- OpenAI (GPT-4o) comme fournisseur de secours
- Ollama local en repli ou en mode confidentialite

## iPhone & Telegram Integration

### Raccourcis iPhone (Siri / Texte)
Jarvis expose un Webhook pour recevoir des commandes directement depuis votre iPhone.
- **URL** : `http://VOTRE_IP_LAN:8090/webhook/command`
- **Méthode** : `POST`
- **Headers** : `Authorization: Bearer VOTRE_WS_TOKEN` (si configuré)
- **Body (JSON)** : `{"text": "votre commande ici"}`

### Bot Telegram
Vous pouvez piloter Jarvis par message via un bot privé.
1. Créez un bot via [@BotFather](https://t.me/botfather).
2. Ajoutez `TELEGRAM_TOKEN=votre_token` dans `.env`.
3. (Optionnel) Ajoutez `TELEGRAM_CHAT_ID=votre_id` pour que Jarvis ne réponde qu'à vous.

Configurez le comportement dans `.env`:

```bash
JARVIS_BRAIN_MODE=balanced   # balanced | speed | smart | privacy
JARVIS_BRAIN_ORDER=gemini,groq,mistral,grok,ollama
```

Les metriques de latence/echec sont stockees dans `logs/ai_router_metrics.json`.
Si un fournisseur tombe en erreur, Jarvis le met temporairement en retrait et
bascule sur le suivant sans casser la conversation.

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

## Home Assistant portable

Le backend garde des alias historiques dans `main2.py`, mais la couche portable
se configure via `jarvis_devices.json`:

- `aliases` mappe les noms prononces vers les vraies entites Home Assistant
- `sensitive_actions` active ou desactive les confirmations
- les entites peuvent aussi etre decouvertes dynamiquement via l'API `/api/states`

Le fichier versionne est `jarvis_devices.example.json`. La copie locale
`jarvis_devices.json` est ignoree par Git.

## Securite

- websocket protege par token via `JARVIS_WS_TOKEN`
- journal d'audit JSONL dans `logs/audit.jsonl`
- confirmation vocale obligatoire pour les actions sensibles
- secrets locaux ignores par Git (`.env`, `credentials.json`, `jarvis_devices.json`)

En mode local simple, laissez `JARVIS_WS_TOKEN=CHANGE_ME` pour des tests rapides.
Pour une installation reseau ou domotique reelle, remplacez-le par un token fort.

## Satellites

L'interface mobile peut servir de satellite vocal sur le reseau local:

- ouvrez `http://IP_DU_SERVEUR:8080`
- ajoutez `?token=VOTRE_TOKEN` a l'URL pour un appairage direct
- le client memorise ensuite le token dans le navigateur

L'architecture recommandee est:

- `main2.py` pour l'orchestration locale
- Home Assistant OS pour la domotique
- clients web/mobile comme satellites
- alias et politique de securite dans `jarvis_devices.json`
