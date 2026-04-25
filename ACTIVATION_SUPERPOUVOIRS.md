# 🌟 PHOEBUS — Activation Superpouvoirs (Démarrage Rapide)

## ⚡ En 5 Minutes

```bash
# 1. Configuration optimisée
cp .env.phoebus-superpouvoirs .env

# 2. Installer dépendances critiques
pip install -U webrtcvad silero-vad soundfile opencv-python faster-whisper

# 3. Tester audio
python3 -c \"from PHOEBUS.audio_optimization import check_hallucination; print(check_hallucination('Merci de votre écoute'))\"

# 4. Découvrir caméras
python3 -c \"from PHOEBUS.network_cameras import discover_cameras; print(discover_cameras())\"

# 5. Lancer PHOEBUS
python main2.py
```

---

## 📊 État des 7 Super-Pouvoirs

| # | Pouvoir | Statut | Prérequis |
|---|---------|--------|-----------|
| 👁️  | Vision Augmentée | ✅ Prêt | OpenCV + Caméra/IP |
| 🖥️  | Overlord (Contrôle) | ✅ Prêt | PyAutoGUI |
| 🛡️  | Sentinelle (Bio) | ✅ Prêt | `PHOEBUS_MULTI_USER=1` |
| 🌍 | Traducteur Universel | ✅ Prêt | Gemini API |
| 🧠 | Conscience Contextuelle | ✅ Prêt | RAG + mémoire |
| 🎭 | Animus (Hologramme) | ✅ Prêt | Frontend Three.js |
| 🌀 | Polymorphe (Morphes) | ✅ Prêt | Frontend animé |

---

## 🎯 Configuration Minimale Recommandée

### .env Essentiel

```bash
# Audio robuste (CRITIQUE)
PHOEBUS_AUDIO_OPTIMIZATION=1
PHOEBUS_ENABLE_AEC=1
PHOEBUS_VAD_MODE=2

# Caméras multiples
PHOEBUS_ENABLE_NETWORK_CAMERAS=1
PHOEBUS_PHONE_IP=192.168.1.100

# Multi-utilisateurs
PHOEBUS_MULTI_USER=1

# LMArena (optionnel mais recommandé)
PHOEBUS_ARENA_BRIDGE_AUTO_START=auto
ARENA_TIMEOUT=60

# IA intelligente
PHOEBUS_BRAIN_MODE=smart
```

---

## 🚀 Démarrage Étapes-par-Étapes

### 1. Audio Sans Écho ✅

```bash
# Installer dépendances audio
brew install portaudio  # macOS
pip install webrtcvad silero-vad soundfile

# Tester hallucination detection
python3 << 'EOF'
from PHOEBUS.audio_optimization import check_hallucination
is_hall, conf = check_hallucination(\"Merci de votre écoute\")
print(f\"Hallucination: {is_hall}, Confiance: {conf:.1%}\")
EOF
```

### 2. Caméras Multiples ✅

```bash
# Découvrir caméras réseau
python3 << 'EOF'
from PHOEBUS.network_cameras import discover_cameras
cameras = discover_cameras()
print(f\"Caméras trouvées: {len(cameras)}\")
for cam in cameras:
    print(f\"  - {cam['name']}\")
EOF

# Capturer depuis caméra
python3 << 'EOF'
from PHOEBUS.network_cameras import get_camera_manager
manager = get_camera_manager()
image = manager.capture(\"phone\")  # ou \"pc\" pour webcam
if image:
    print(f\"Capture OK: {image.size}\")
EOF
```

### 3. LMArena (Réflexion Profonde) ✅

```bash
# Cloner et configurer LMArenaBridge
cd external
git clone https://github.com/CloudWaddie/LMArenaBridge.git
cd LMArenaBridge

# Voir GUIDE_SUPERPOUVOIRS.md pour configuration

# Lancer le bridge
python main.py

# Vérifier disponibilité
curl http://localhost:8000/api/v1/models
```

### 4. Multi-Utilisateurs ✅

```bash
# Activer dans .env
PHOEBUS_MULTI_USER=1

# Enregistrer utilisateur
python3 << 'EOF'
from PHOEBUS.multi_user import enregistrer_voix
# PHOEBUS demandera 30s d'enregistrement vocal
EOF

# PHOEBUS identifiera automatiquement qui parle
```

### 5. Performance Optimale ✅

```bash
# Profil rapide (< 2s réponse)
PHOEBUS_BRAIN_MODE=speed
PHOEBUS_WHISPER_MODEL=tiny

# OU profil qualité (meilleure réponse)
PHOEBUS_BRAIN_MODE=smart
PHOEBUS_WHISPER_MODEL=small
PHOEBUS_ARENA_BRIDGE_AUTO_START=auto
```

---

## 🧪 Tests Rapides

### Test Audio

```bash
python3 scripts/test_audio.py
```

### Test Caméras

```bash
python3 scripts/test_vision.py
```

### Test STT

```bash
python3 scripts/test_mic.py
```

### Diagnostic Complet

```bash
python3 scripts/diagnose.py
```

---

## 📚 Documentation

| Document | Contenu |
|----------|---------|
| `DIAGNOSTIC_PHOEBUS_COMPLETE.md` | Audit complet (71 points) |
| `GUIDE_SUPERPOUVOIRS.md` | Guide détaillé activation |
| `.env.phoebus-superpouvoirs` | Configuration complète |
| `setup_superpouvoirs.py` | Script setup automatisé |

---

## 🔍 Troubleshooting Rapide

### \"Pas de son\"

```bash
brew install portaudio
pip install pyaudio
```

### \"Hallucinations détectées\"

```bash
# Vérifier VAD
PHOEBUS_VAD_MODE=3  # Plus agressif
```

### \"Caméra réseau pas trouvée\"

```bash
# Vérifier IP du téléphone
ping 192.168.1.100
# Installer app IP Webcam (Android)
```

### \"LMArena connexion refusée\"

```bash
# Vérifier bridge
curl http://localhost:8000/api/v1/health
# Relancer si nécessaire
python external/LMArenaBridge/main.py
```

### \"Latence trop élevée (> 3s)\"

```bash
# Voir metrics
python scripts/diagnose.py

# Réduire modèles
PHOEBUS_WHISPER_MODEL=tiny
PHOEBUS_BRAIN_MODE=speed
```

---

## ✅ Checklist Activation

- [ ] `.env` copié et configuré
- [ ] Dépendances audio installées + testées
- [ ] Caméras découvertes et listées
- [ ] LMArena cloned (optionnel)
- [ ] Multi-utilisateurs activé
- [ ] Tests passés ✅
- [ ] `python main2.py` lancé
- [ ] Avatar actif et animé

---

## 📞 Support Rapide

Tous les modules ont des docstrings complets :

```python
from PHOEBUS.audio_optimization import get_processor
help(get_processor)

from PHOEBUS.network_cameras import discover_cameras
help(discover_cameras)
```

Voir aussi: `GUIDE_SUPERPOUVOIRS.md` pour support détaillé.

---

## 🎬 Résultat Attendu

```
🌟 PHOEBUS — Systèmes Actifs
════════════════════════════
✅ Audio               Sans écho, VAD robuste, AEC actif
✅ Vision              Webcam PC + caméra téléphone + réseau
✅ Intelligence        LMArena pour réflexion, Gemini pour chat
✅ Multi-utilisateurs  Reconnaît voix, adapte réponses
✅ Hologramme          Avatar animé + morphes géométriques
✅ Performance         Latence < 2s, 60 FPS animations
✅ Sécurité            Token WebSocket, authentification réseau

🚀 Prêt pour conversation avec Floriace!
```

---

**Document:** 26 avril 2026  
**Version:** SUPERPOUVOIRS v1.0  
**Pour:** Floriace  
**Status:** ✅ Production Ready
