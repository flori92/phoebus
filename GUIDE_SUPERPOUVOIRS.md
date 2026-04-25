# 🌟 PHOEBUS — Guide d'Activation des 7 Super-Pouvoirs

## 📌 Vue d'Ensemble Rapide

PHOEBUS possède désormais tous les éléments critiques pour fonctionner à 100%. Ce guide vous montre comment :
1. ✅ Configurer l'audio sans écho ni hallucinations
2. ✅ Accéder aux caméras réseau (PC + téléphone + NVR)
3. ✅ Utiliser LMArena pour la réflexion profonde
4. ✅ Activer la reconnaissance multi-utilisateurs
5. ✅ Optimiser la performance globale

---

## 🚀 Démarrage Rapide (5 minutes)

### Étape 1 : Copier la Configuration Optimisée

```bash
cd /Users/floriace/Jarvis

# Activer la configuration des super-pouvoirs
cp .env.phoebus-superpouvoirs .env

# OU fusionner avec votre .env existant
cat .env.phoebus-superpouvoirs >> .env
```

### Étape 2 : Installer les Dépendances Audio/Vision

```bash
# Macros: installer portaudio (nécessaire pour PyAudio)
brew install portaudio

# Installer/mettre à jour dépendances
pip install -U --no-cache-dir \
    webrtcvad \
    soundfile \
    silero-vad \
    faster-whisper \
    opencv-python \
    resemblyzer

# (Optionnel) Si vous avez un GPU NVIDIA
pip install onnxruntime-gpu
```

### Étape 3 : Tester l'Audio

```bash
python3 -c \"
from PHOEBUS.audio_optimization import get_processor, check_hallucination

# Test 1: Hallucination
is_hall, conf = check_hallucination('Merci de votre écoute')
print(f'Test hallucination: {is_hall} (confiance: {conf:.2f})')

# Test 2: Texte normal
is_hall2, conf2 = check_hallucination('Bonjour comment ça va')
print(f'Test normal: {is_hall2} (confiance: {conf2:.2f})')
\"
```

### Étape 4 : Découvrir les Caméras

```bash
python3 -c \"
from PHOEBUS.network_cameras import discover_cameras

print('Scan réseau...')
cameras = discover_cameras()
print(f'Caméras trouvées: {len(cameras)}')
for cam in cameras:
    print(f'  - {cam.get(\\\"name\\\")} : {cam.get(\\\"url\\\")}')
\"
```

### Étape 5 : Configurer LMArena (Optionnel mais Recommandé)

```bash
# Cloner LMArenaBridge
cd external
git clone https://github.com/CloudWaddie/LMArenaBridge.git
cd LMArenaBridge

# Créer config.json avec vos credentials
# (Voir section LMArena ci-dessous)
```

---

## 🎙️ Audio Sans Écho

### Problème Résolu

**Avant :**
- ❌ PHOEBUS parlait, puis captait sa propre parole  
- ❌ Hallucinations type \"Merci de votre écoute\"
- ❌ Bruit blanc constant

**Après :**
- ✅ Détection écho + suppression (AEC)
- ✅ Filtre hallucinations IA intelligent
- ✅ Noise gate + AGC automatique

### Configuration Audio (.env)

```bash
# ✅ Tous les filtres activés (recommandé)
PHOEBUS_AUDIO_OPTIMIZATION=1
PHOEBUS_ENABLE_AEC=1              # Suppression écho
PHOEBUS_ENABLE_NOISE_GATE=1       # Filtre bruit
PHOEBUS_ENABLE_AGC=1              # Normalisation gain
PHOEBUS_VAD_MODE=2                # Détection parole (0-3, défaut=2)
PHOEBUS_NOISE_THRESHOLD=0.02      # Seuil silence (bas=sensible)
PHOEBUS_STT_BACKEND=auto          # Meilleur STT disponible
PHOEBUS_WHISPER_MODEL=small       # Équilibre vitesse/qualité
```

### Options Audio Avancées

```bash
# Pour environnement très bruyant :
PHOEBUS_VAD_MODE=3               # Hyper-agressif
PHOEBUS_NOISE_THRESHOLD=0.05     # Plus permissif

# Pour milieu calme (bureau) :
PHOEBUS_VAD_MODE=1               # Moins agressif
PHOEBUS_NOISE_THRESHOLD=0.01     # Plus sensible

# Pour vitesse ultra-rapide (latence < 1s) :
PHOEBUS_WHISPER_MODEL=tiny       # Tiny mais bien
PHOEBUS_STT_BACKEND=groq         # API Groq (plus rapide)

# Pour qualité maximale :
PHOEBUS_WHISPER_MODEL=medium
PHOEBUS_STT_BACKEND=auto
```

### Test Audio

```bash
#!/bin/bash
cd /Users/floriace/Jarvis

# Test 1: Hallucination detection
python3 << 'EOF'
from PHOEBUS.audio_optimization import check_hallucination

tests = [
    \"Merci de votre écoute\",
    \"Sous-titres par Amara.org\",
    \"Bonjour, comment allez-vous?\",
    \"Qu'est-ce que tu fais?\",
]

for text in tests:
    is_hall, conf = check_hallucination(text)
    status = \"❌ HALLUCINATION\" if is_hall else \"✅ VALIDE\"
    print(f\"{status} : '{text}' (confiance: {conf:.1%})\")
EOF

# Test 2: Microphone en direct
python3 scripts/test_mic.py
```

---

## 👁️ Caméras Multiples (PC + Téléphone + Réseau)

### Configuration Caméras (.env)

```bash
# Caméra réseau
PHOEBUS_ENABLE_NETWORK_CAMERAS=1
PHOEBUS_CAMERA_SCAN_TIMEOUT=5.0

# Votre téléphone (ex: app IP Webcam Android)
PHOEBUS_PHONE_IP=192.168.1.100

# NVR ou caméra principale (optionnel)
PHOEBUS_NVR_IP=192.168.1.50

# Reconnaissance faciale
PHOEBUS_ENABLE_FACE_RECOGNITION=1
```

### Découvrir Caméras Automatiquement

```bash
python3 << 'EOF'
from PHOEBUS.network_cameras import discover_cameras, get_camera_manager

# Découvrir toutes les caméras
cameras = discover_cameras()
print(f\"\\n🎥 {len(cameras)} caméra(s) trouvée(s):\")
for cam in cameras:
    print(f\"   • {cam['name']:20} {cam.get('url', 'local')}\")

# Tester capture depuis chaque caméra
manager = get_camera_manager()
print(\"\\nTest capture...\" )
for cam_name in manager.list_cameras():
    image = manager.capture(cam_name)
    if image:
        print(f\"   ✓ {cam_name}: Image capturée ({image.size})\")
    else:
        print(f\"   ✗ {cam_name}: Erreur\")
EOF
```

### Ajouter Caméra Manuellement

```python
# Dans PHOEBUS ou script
from PHOEBUS.network_cameras import get_camera_manager

manager = get_camera_manager()

# Téléphone via IP Webcam
manager.register_camera(\"phone\", {
    \"name\": \"phone\",
    \"url\": \"http://192.168.1.100:8080\",
    \"protocol\": \"http\",
    \"type\": \"mobile\"
})

# Caméra IP RTSP
manager.register_camera(\"salon\", {
    \"name\": \"salon\",
    \"url\": \"rtsp://192.168.1.50:554/stream\",
    \"protocol\": \"rtsp\",
    \"type\": \"ip_camera\"
})
```

### Utiliser Caméra dans Vision PHOEBUS

```python
from PHOEBUS.vision import demander_ia_vision
from PHOEBUS.network_cameras import get_camera_manager

manager = get_camera_manager()

# Capturer depuis téléphone
image = manager.capture(\"phone\")

# Analyser avec IA
if image:
    result = await demander_ia_vision(image, \"Que vois-tu sur l'écran?\")
    print(result)
```

---

## 🧠 LMArena — Super-Cerveau pour Réflexion Profonde

### Qu'est-ce que LMArena?

LMArena Bridge vous donne accès **gratuitement** à :
- **Claude 3.5 Sonnet** (meilleur modèle Claude)
- **GPT-4o** (meilleur modèle OpenAI)
- **Gemini Pro** (meilleur modèle Google)

C'est un bridge local qui route vos requêtes vers ces modèles sans que vous ayez besoin de clés API.

### Installation LMArena

```bash
cd /Users/floriace/Jarvis/external

# Cloner le repo
git clone https://github.com/CloudWaddie/LMArenaBridge.git
cd LMArenaBridge

# Installer dépendances
pip install -r requirements.txt

# Vérifier installation
python main.py --help
```

### Configuration LMArena

1. **Créer `config.json`** :

```bash
cd /Users/floriace/Jarvis/external/LMArenaBridge

# Copier exemple (s'il existe)
cp config.example.json config.json

# OU créer manuellement:
cat > config.json << 'EOF'
{
  \"auth\": {
    \"arena_auth_token\": \"\",
    \"arena_auth_prod_v1\": \"\",
    \"claude_auth\": \"\",
    \"openai_auth\": \"\"
  },
  \"api\": {
    \"port\": 8000,
    \"host\": \"127.0.0.1\"
  },
  \"models\": {
    \"default_model\": \"claude-3-5-sonnet\",
    \"available\": [\"claude-3-5-sonnet\", \"gpt-4o\", \"gemini-pro\"]
  }
}
EOF
```

2. **Configurer les credentials** :

Consultez [LMArenaBridge README](https://github.com/CloudWaddie/LMArenaBridge) pour obtenir vos tokens.

3. **Lancer le bridge** :

```bash
# Manuelle
cd /Users/floriace/Jarvis/external/LMArenaBridge
python main.py

# OU automatique (via PHOEBUS)
cd /Users/floriace/Jarvis
python scripts/arena_bridge.py start
```

4. **Tester le bridge** :

```bash
curl http://localhost:8000/api/v1/models
# Devrait retourner la liste des modèles disponibles
```

### Configuration PHOEBUS pour LMArena

```bash
# .env
ARENA_URL=http://localhost:8000/api/v1
ARENA_MODEL=claude-3-5-sonnet
ARENA_DEEP_MODEL=claude-3-5-sonnet
ARENA_TIMEOUT=60
PHOEBUS_BRAIN_MODE=smart
PHOEBUS_ARENA_BRIDGE_AUTO_START=auto
```

### Résultat

Quand PHOEBUS détecte une requête \"profonde\" (analyse, réflexion, architecture) :
- Il utilise **Claude Sonnet** automatiquement
- Résultat réfléchi et nuancé
- Cache des réponses pour performance

---

## 👤 Multi-Utilisateurs & Biométrie

### Activation

```bash
# .env
PHOEBUS_MULTI_USER=1
PHOEBUS_SPEAKER_THRESHOLD=0.75
PHOEBUS_ENABLE_FACE_RECOGNITION=1
```

### Enregistrer un Utilisateur

```bash
python3 << 'EOF'
from PHOEBUS.multi_user import enregistrer_voix
import speech_recognition as sr

# Enregistrement vocal (30 secondes)
recognizer = sr.Recognizer()
with sr.Microphone() as source:
    print(\"Parlez pendant 30 secondes...\")
    audio = recognizer.record(source, duration=30)

# Enregistrer
enregistrer_voix(\"Floriace\", audio)
print(\"✓ Profil vocal enregistré pour Floriace\")
EOF
```

### Utilisation Automatique

PHOEBUS identifie automatiquement qui parle et adapte ses réponses :
- Tutoiement pour Floriace
- Comportement personnalisé
- Accès différenciés selon profil

---

## ⚡ Performance & Latence

### Mesurer Latence Actuelle

```bash
python3 scripts/diagnose.py
```

Affiche:
- Temps STT (speech-to-text)
- Temps LLM (réponse IA)
- Temps TTS (synthèse vocale)
- **Latence totale**

### Optimiser pour Rapidité

```bash
# .env - Profil \"SPEED\" (< 2 secondes)
PHOEBUS_BRAIN_MODE=speed
PHOEBUS_WHISPER_MODEL=tiny
PHOEBUS_STT_BACKEND=groq
PHOEBUS_ENABLE_IA_STREAMING=1
PHOEBUS_ENABLE_PARALLEL_PROCESSING=1
PHOEBUS_ARENA_BRIDGE_AUTO_START=off  # Désactiver (trop lent)
```

### Optimiser pour Qualité

```bash
# .env - Profil \"SMART\" (meilleure réponse)
PHOEBUS_BRAIN_MODE=smart
PHOEBUS_WHISPER_MODEL=small
PHOEBUS_ENABLE_LIPSYNC=1
PHOEBUS_ARENA_BRIDGE_AUTO_START=auto  # Utiliser LMArena
```

---

## 🔐 Sécurité & Token WebSocket

### Changer Token WebSocket

```bash
# Générer nouveau token
PHOEBUS_WS_TOKEN=$(python3 -c \"import secrets; print(secrets.token_urlsafe(32))\")

# Mettre à jour .env
sed -i \"\" \"s/PHOEBUS_WS_TOKEN=.*/PHOEBUS_WS_TOKEN=$PHOEBUS_WS_TOKEN/\" .env
```

### Activer Authentification

```bash
# .env
WS_AUTH_REQUIRED=1
PHOEBUS_WS_TOKEN=votre_token_securise_ici
```

---

## 🧪 Tests Complets

### Suite de Tests Automatisés

```bash
#!/bin/bash

echo \"🧪 Suite de Tests PHOEBUS\"
echo \"=========================\"

# Test 1: Audio
echo \"\\n1️⃣ Audio Optimization...\"
python3 -m pytest PHOEBUS/tests/test_audio.py -v

# Test 2: Vision
echo \"\\n2️⃣ Network Cameras...\"
python3 -m pytest PHOEBUS/tests/test_vision.py -v

# Test 3: STT
echo \"\\n3️⃣ Speech Recognition...\"
python3 -m pytest PHOEBUS/tests/test_stt.py -v

# Test 4: LMArena
echo \"\\n4️⃣ LMArena Bridge...\"
curl -s http://localhost:8000/api/v1/models | jq .

echo \"\\n✅ Tests terminés\"
```

---

## 📊 Monitoring & Logs

### Voir les Logs en Direct

```bash
# Logs PHOEBUS
tail -f logs/phoebus.log

# Logs Arena Bridge (si actif)
tail -f logs/arena_bridge.log

# Logs audit (actions sensibles)
tail -f logs/audit.jsonl | jq .

# Tous les logs
tail -f logs/*.log logs/*.jsonl
```

### Métriques Audio

```bash
# Afficher statistiques STT/LLM
python3 << 'EOF'
import json
from pathlib import Path

metrics = json.loads(Path('logs/ai_router_metrics.json').read_text())
print(\"Métriques fournisseurs IA:\")
for provider, stats in metrics.items():
    print(f\"{provider:15} {stats}\")
EOF
```

---

## 🎯 Checklist Complet

- [ ] Audio activé + testé
- [ ] Caméras découvertes + configurées
- [ ] LMArena installé + bridge lancé
- [ ] Multi-utilisateurs activé
- [ ] Token WebSocket changé
- [ ] Tests passés ✅
- [ ] Latence acceptée (< 3s)
- [ ] Logs supervisés

---

## 🆘 Troubleshooting

### Audio : \"Pas de son de sortie\"

```bash
# Vérifier PyAudio
python3 -c \"import pyaudio; print('PyAudio OK')\"

# Vérifier portaudio sur Mac
brew info portaudio
```

### Caméras : \"Pas trouvées\"

```bash
# Vérifier OpenCV
python3 -c \"import cv2; print('OpenCV OK')\"

# Vérifier IP du téléphone
ping 192.168.1.100

# Scanner réseau manuellement
python3 PHOEBUS/network_cameras.py
```

### LMArena : \"Connexion refusée\"

```bash
# Vérifier que le bridge est lancé
curl http://localhost:8000/api/v1/health

# Relancer le bridge
python scripts/arena_bridge.py start

# Vérifier les logs
tail -f logs/arena_bridge.log
```

### Performance : \"Trop lent\"

```bash
# Lancer diagnostic
python3 scripts/diagnose.py

# Profiler hot paths
python3 -m cProfile -s cumtime phoebus_agent.py | head -20
```

---

## 📞 Support

Tous les fichiers ont des docstrings complètes :

```python
# Aide directement dans le code
from PHOEBUS.audio_optimization import get_processor
help(get_processor)

from PHOEBUS.network_cameras import discover_cameras
help(discover_cameras)
```

---

**Document généré:** 26 avril 2026  
**Pour:** Floriace  
**Maintenance:** Consulter DIAGNOSTIC_PHOEBUS_COMPLETE.md
