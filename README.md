# PHOEBUS

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
avec npm, cree `.env` si besoin et prepare `phoebus_devices.json` a partir du modele.

## Configuration

1. Copiez `.env.example` vers `.env` si le bootstrap ne l'a pas deja fait.
2. Renseignez les cles utiles: Gemini, Home Assistant, YouTube, SerpAPI, Groq/xAI.
3. Adaptez `phoebus_devices.json` aux entites de votre Home Assistant.
4. Pour Google Docs/Gmail/Calendar, placez `credentials.json` a la racine.

## Cerveau multi-provider

PHOEBUS route maintenant chaque requete vers le meilleur cerveau disponible:

- fast-path local pour les commandes evidentes (domotique, heure, date)
- Gemini pour les requetes complexes, la recherche outillee et la vision
- Groq pour les reponses texte tres rapides
- Grok/xAI pour les sujets X/Twitter, les requetes temps reel orientees actualite
- Arena via LMArenaBridge local pour acceder aux modeles gratuits exposes par LM Arena
- Mistral comme cerveau francophone/europeen secondaire
- OpenAI (GPT-4o) comme fournisseur de secours
- Ollama local en repli ou en mode confidentialite

## iPhone & Telegram Integration

### Raccourcis iPhone (Siri / Texte)
PHOEBUS expose un Webhook pour recevoir des commandes directement depuis votre iPhone.
- **URL** : `http://VOTRE_IP_LAN:8090/webhook/command`
- **Méthode** : `POST`
- **Body (JSON)** : `{"text": "votre commande ici"}`

### Bot Telegram
Vous pouvez piloter PHOEBUS par message via un bot privé.
1. Créez un bot via [@BotFather](https://t.me/botfather).
2. Ajoutez `TELEGRAM_TOKEN=votre_token` dans `.env`.
3. (Optionnel) Ajoutez `TELEGRAM_CHAT_ID=votre_id` pour que PHOEBUS ne réponde qu'à vous.

Configurez le comportement dans `.env`:

```bash
PHOEBUS_BRAIN_MODE=balanced   # balanced | speed | smart | privacy
PHOEBUS_BRAIN_ORDER=gemini,groq,grok,arena,mistral,openai,ollama
```

Les metriques de latence/echec sont stockees dans `logs/ai_router_metrics.json`.
Si un fournisseur tombe en erreur, PHOEBUS le met temporairement en retrait et
bascule sur le suivant sans casser la conversation.

## Bridge Arena gratuit

PHOEBUS sait utiliser un bridge OpenAI-compatible local vers LM Arena. Le code du
bridge reste dans `external/LMArenaBridge` et ses cookies restent hors Git.

1. Ajoutez dans `.env` le cookie `arena-auth-prod-v1` complet si vous en avez un:
   `ARENA_AUTH_PROD_V1=base64-...`
2. Lancez l'installation du bridge:
   `.venv/bin/python scripts/arena_bridge.py setup --install`
3. Demarrez PHOEBUS normalement. Avec `PHOEBUS_ARENA_BRIDGE_AUTO_START=auto`,
   `main2.py` lance le bridge quand un token Arena ou un `config.json` local existe.

`ARENA_URL` doit pointer vers `http://localhost:8000/api/v1` et `ARENA_API_KEY`
doit rester identique a la cle configuree dans le bridge, par defaut `arena`.
Sans cookie, `PHOEBUS_ARENA_BRIDGE_ALLOW_ANONYMOUS=1` autorise le bridge a tenter
la session anonyme geree par LMArenaBridge.
PHOEBUS interroge `/api/v1/models` et choisit automatiquement le premier modele
Arena disponible dans `ARENA_MODEL_CANDIDATES` ou `ARENA_DEEP_MODEL_CANDIDATES`.
Les appels Arena utilisent le streaming pour permettre au bridge de basculer sur
son transport navigateur quand aucun token n'est configure.
Les logs du bridge lance par `main2.py` vont dans `logs/arena_bridge.log`.

## Lancement

```bash
.venv/bin/python main2.py
```

Ou:

```bash
./demarrer_phoebus.sh
```

Sur Windows, utilisez `DÉMARRER_PHOEBUS.bat`.

## Diagnostic

```bash
.venv/bin/python scripts/doctor.py
.venv/bin/python scripts/diagnose.py
```

`doctor.py` donne un diagnostic synthétique de l'environnement actif :
dépendances voix/STT, configuration, runtime unique, frontend et endpoint
`/health`. Ajoutez `--json` pour une sortie exploitable par un script.

PyAudio est optionnel. S'il ne s'installe pas, le micro PC et les applaudissements
sont desactives, mais le backend et l'interface mobile restent utilisables.

## Home Assistant portable

Le backend garde des alias historiques dans `main2.py`, mais la couche portable
se configure via `phoebus_devices.json`:

- `aliases` mappe les noms prononces vers les vraies entites Home Assistant
- `sensitive_actions` active ou desactive les confirmations
- les entites peuvent aussi etre decouvertes dynamiquement via l'API `/api/states`

Le fichier versionne est `phoebus_devices.example.json`. La copie locale
`phoebus_devices.json` est ignoree par Git.

## Securite

- websocket local avec pairing par appareil, sans token dans l'URL
- journal d'audit JSONL dans `logs/audit.jsonl`
- confirmation vocale obligatoire pour les actions sensibles
- secrets locaux ignores par Git (`.env`, `credentials.json`, `phoebus_devices.json`)

## Satellites

L'interface mobile peut servir de satellite vocal sur le reseau local:

- ouvrez `http://IP_DU_SERVEUR:8080`
- l'app se connecte directement au WebSocket local
- le micro mobile se relance automatiquement apres chaque segment de parole

L'architecture recommandee est:

- `main2.py` pour l'orchestration locale
- Home Assistant OS pour la domotique
- clients web/mobile comme satellites
- alias et politique de securite dans `phoebus_devices.json`
