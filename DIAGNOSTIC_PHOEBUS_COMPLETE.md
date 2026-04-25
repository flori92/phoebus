# 🌟 DIAGNOSTIC COMPLET PHOEBUS — Avril 2026

## Rapport d'Audit des 7 Super-Pouvoirs

Ce document analyse l'état actuel de PHOEBUS et propose des optimisations pour garantir performance, qualité d'écoute, et intelligence maximale.

---

## 📋 État Général

| Composant | Statut | Notes |
|-----------|--------|-------|
| **Backend (Python 3.13)** | ✅ Opérationnel | Tous imports rebrandé PHOEBUS |
| **Frontend (React/Three.js)** | ✅ Opérationnel | Vite, animations WebGL |
| **WebSocket** | ✅ Opérationnel | Port 8765, authentification HMAC |
| **LMArena Bridge** | ⚠️ Partiel | Intégré mais pas optimisé pour profondeur |
| **Vision (Caméra PC)** | ✅ Opérationnel | OpenCV + Gemini Vision API |
| **Voice (STT/TTS)** | ⚠️ À Améliorer | VAD présent, AEC absent |

---

## 👁️ Super-Pouvoir 1 : Vision Augmentée

### État Actuel
```
✅ Capture d'écran         → Oui (pyautogui + frontend)
✅ Identification d'objets  → Oui (Gemini Vision)
✅ OCR texte               → Oui (Gemini Vision)
✅ Caméra PC (webcam)      → Oui (cv2, index 0)
❌ Caméra réseau (IP)      → Partiellement (config existe, pas testé)
❌ Énumération auto        → Non (PHOEBUS_CAMERA_IP en hardcoded)
❌ Multi-caméras sync      → Non
❌ Face recognition        → Non (prêt pour resemblyzer)
```

### Problèmes Identifiés
1. **PHOEBUS_CAMERA_IP** uniquement—pas de découverte automatique des caméras IP sur le réseau
2. Pas de fallback si la caméra n'est pas accessible
3. Pas de format standardisé pour les URL de caméras (RTSP, HTTP, WebRTC)
4. Identification de visage manquante (vous avez le code pour resemblyzer mais pas activé)

### Recommandations
- ✅ Créer module `network_cameras.py` pour scanner/enregistrer caméras réseau
- ✅ Supporter RTSP, HTTP, WebRTC
- ✅ Ajouter reconnaissance faciale via resemblyzer
- ✅ Cacher caméras locales au boot (scan réseau local)

---

## 🖥️ Super-Pouvoir 2 : Overlord (Contrôle Système)

### État Actuel
```
✅ Verrouillage session      → Oui (macOS via AppleScript)
✅ Mise en veille Mac        → Oui
✅ Vider corbeille           → Oui
✅ Gestion fichiers/dossiers → Oui
✅ Ouverture apps           → Oui
✅ Gestion volume/audio     → Partiellement
❌ AppleScript avancé       → Peu utilisé
❌ Automation Shortcuts      → Non
❌ Terminal/shell direct    → Limité
```

### Problèmes Identifiés
1. AppleScript non utilisé pour les commandes système avancées
2. Pas d'interface vers Automator/Shortcuts
3. Shell commands restreintes (sécurité)

### Recommandations
- ✅ Améliorer intégration AppleScript (déjà du code pour ça)
- ✅ Supporter notifications système
- ✅ Ajouter exécution script shell contrôlée

---

## 🛡️ Super-Pouvoir 3 : Sentinelle (Biométrie & Empathie)

### État Actuel
```
✅ Multi-utilisateurs        → Oui (mais PHOEBUS_MULTI_USER=0 par défaut)
✅ Identification vocale     → Oui (resemblyzer + MFCC fallback)
✅ Reconnaissance faciale    → Prêt (code présent, pas activé)
✅ Analyse humeur            → Partiellement (probing texte uniquement)
❌ Détection fatigue visuelle→ Non
❌ Biométrique continue      → Non
```

### Problèmes Identifiés
1. `PHOEBUS_MULTI_USER=0` par défaut—reconnaissance désactivée
2. Pas d'analyse vidéo pour détecter l'humeur (pose, expression)
3. Pas de session biométrique continue

### Recommandations
- ✅ Activer `PHOEBUS_MULTI_USER=1` par défaut
- ✅ Améliorer détection d'humeur (ton de voix + texte)
- ✅ Ajouter analyse faciale légère pour contexte

---

## 🌍 Super-Pouvoir 4 : Traducteur Universel

### État Actuel
```
✅ Traduction basique         → Oui (Gemini)
⚠️ Traduction temps réel      → Faisable mais lent
❌ Interprète live            → Non
❌ Détection auto langue      → Limitée
❌ Reconnaissance accentage   → Non
```

### Problèmes Identifiés
1. Traduction sur-demande uniquement (pas de flux continu)
2. Pas de détection auto de la langue d'entrée
3. Latence importante pour streaming traduction

### Recommandations
- ✅ Implémenter streaming traduction (LMArena pour rapidité)
- ✅ Ajouter détection auto-langue
- ✅ Cache traductions fréquentes

---

## 🧠 Super-Pouvoir 5 : Conscience Contextuelle (Neural Pulse)

### État Actuel
```
✅ Analyse écran             → Oui (vision.py)
✅ Proactivité               → Oui (proactive.py)
⚠️ Anticipation              → Basique (regex patterns)
✅ Neural Pulse UI           → Oui (orb.ts animation)
❌ Contexte temps réel       → Limité
```

### Problèmes Identifiés
1. Proactivité repose sur patterns simples
2. Pas d'apprentissage des habitudes (sauf mémoire JSON)
3. Neural Pulse pulse mais sans corrélation avec analyse réelle

### Recommandations
- ✅ Améliorer models de prédiction comportementale (timeline + RAG)
- ✅ Lier Neural Pulse à contexte réel (pas juste cosmétique)
- ✅ Ajouter apprentissage des patterns

---

## 🎭 Super-Pouvoir 6 : Animus (Hologramme & Avatar)

### État Actuel
```
✅ Avatar vidéo              → Oui (face-avatar.ts)
✅ Effets glitch cybernétique→ Oui (CSS + WebGL)
✅ Respiration holographique → Oui (orb breathing animation)
✅ Fusion visage/orbe        → Oui (Three.js)
⚠️ Synchronisation lèvres    → Oui mais basique (lipsync.py)
```

### Problèmes Identifiés
1. Lipsync peut être désynchronisé
2. Pas de détection de performance (fallback si lag)
3. Pas d'adaptation qualité vidéo

### Recommandations
- ✅ Améliorer lipsync (modèle ML léger)
- ✅ Ajouter adaptive quality (résolution basée sur perf)

---

## 🌀 Super-Pouvoir 7 : Polymorphe (Morphisme Géométrique)

### État Actuel
```
✅ Toile Spider-Man          → Oui (orb.ts)
✅ Grille Matrix             → Oui (orb.ts)
✅ Vortex Galaxie            → Oui (orb.ts)
✅ Boule Énergie Iron Man    → Oui (orb.ts)
⚠️ Transitions smooth        → Oui mais saccadées parfois
❌ Déformation organique     → Non
```

### Problèmes Identifiés
1. Transitions peuvent être saccadées (framerate instable)
2. Pas d'optimisation GPU
3. Pas de feedback utilisateur sur morphes

### Recommandations
- ✅ Optimiser rendering Three.js (geometry pooling)
- ✅ Ajouter feedback audio pour transitions

---

## 🎙️ PROBLÈME CRITIQUE : Audio (Écho + Hallucinations)

### État Actuel de la Détection Vocale

```python
# PHOEBUS/voice.py
class BargeInMonitor(threading.Thread):
    """Surveillance micro PENDANT la parole de PHOEBUS"""
    ✅ Détecte interruption utilisateur
    ⚠️ Threshold adaptatif manquant
    ❌ Aucune AEC (Acoustic Echo Cancellation)
    ❌ Aucune suppression bruit (noise gating)
    ❌ Aucun AGC (Auto Gain Control)
```

```python
# PHOEBUS/stt_backends.py - Faster Whisper
✅ VAD filter = True (détecte silence)
✅ vad_parameters dict(min_silence_duration_ms=500)
⚠️ Énergie minimum = 0.02 (peut être trop bas)
✅ Détection confiance langue > 0.6
❌ Aucun post-processing hallucinations
```

```python
# PHOEBUS/server.py
✅ Filtre hallucinations STT classiques
❌ Mais seulement pour liste fixe
❌ Pas de détection intelligente d'hallucination
```

### Problèmes Spécifiques

#### 1. **Écho Acoustique**
- Pas de AEC (Acoustic Echo Cancellation) sur le flux entrée
- Impossible de distinguer "je parle" vs "mon micro capte ma sortie audio"
- Solution requise : WebRtcVad + filtrage adaptatif

#### 2. **Hallucinations Whisper**
- Whisper hallucine sur silence ("Sous-titres par Amara.org", "Merci de votre écoute")
- VAD filter existe mais peut rater cas limites
- Solution requise : post-processing IA des transcriptions suspectes

#### 3. **Bruit Ambiant**
- Pas d'AGC (Auto Gain Control) → conversation difficile en milieu bruyant
- Pas de noise gate → capture bruit blanc/ventilateur
- Solution requise : Noise suppression (Noise2Noise ou Silero)

#### 4. **Détection Silence vs. Parole**
- RMS threshold dans BargeInMonitor pas adaptatif
- Peut rater voix faible ou basse
- Solution requise : WebRtcVad (Google, gratuit, ML)

### Recommandations Audio CRITIQUES
- ✅ Ajouter **WebRtcVad** (Google VAD, gratuit, C++)
- ✅ Ajouter **Silero VAD + Noise** (bruit + silence)
- ✅ Implémenter **AEC** via PyAudio + filtrage adaptatif
- ✅ Ajouter **détection hallucinations IA** après transcription
- ✅ Tester sur macOS (PyAudio parfois instable)

---

## 🧠 LMArena - État d'Intégration

### Configuration Actuelle
```python
# PHOEBUS/config.py
ARENA_URL = "http://localhost:8000/api/v1"
ARENA_MODEL = "gemini-2.5-flash" (fallback par défaut)
ARENA_DEEP_MODEL = "claude-sonnet-4-5-20250929" (réflexion profonde)
arena_client = OpenAI(api_key="arena", base_url=ARENA_URL)
```

### Utilisé pour
```python
# PHOEBUS/ai.py
if kind == "deep":
    preferred = preferred or "arena"
```

### Problèmes
1. **Pas utilisé pour streaming** → réponses lentes
2. **Fallback uniquement** → pas de priorité intelligente
3. **Timeout à 30s** → trop court pour réflexion profonde
4. **Pas de cache** des réponses Arena (coûteux)

### Recommandations
- ✅ Faire LMArena prioritaire pour tâches "deep"
- ✅ Augmenter timeout à 60s pour réflexion
- ✅ Ajouter cache des réponses (Redis ou fichier)
- ✅ Supporter streaming via SSE (EventStream)
- ✅ Alerter Floriace quand Arena utilisé (log, UI feedback)

---

## ⚡ Performance & Latence

### Metrics Actuelles (estimées)
| Opération | Latence | Goulot |
|-----------|---------|--------|
| STT (Whisper) | 500-1500ms | Modèle local |
| LLM (Gemini) | 800-2000ms | Réseau |
| TTS (Edge) | 300-800ms | Synthèse |
| Vision | 1500-3000ms | API call + traitement |
| **Temps Total** | **2.6-5.6s** | STT + LLM |

### Optimisations Actuelles
```
✅ Faster-Whisper (M1/M2 optimisé)
✅ Streaming réponse IA (parole par phrase)
✅ Cache réponses (response_cache.py)
✅ Router brain intelligent (brain_router.py)
⚠️ Parallélisation STT + analyse limitée
❌ GPU acceleration (peut aider sur Mac)
```

### Recommandations
- ✅ Passer de `whisper-base` à `whisper-tiny` pour vitesse (si précision ok)
- ✅ Augmenter `beam_size` Whisper de 5 à 3 (plus rapide, moins précis)
- ✅ Implémenter streaming LLM via SSE (répondre plus vite)
- ✅ Paralléliser STT + mémoire retrieval (RAG)
- ✅ Profiler avec `cProfile` et optimiser hot paths

---

## 🔐 Sécurité & Hallucinations

### Filtres Actuels
```python
# PHOEBUS/server.py
HALLUCINATIONS_STT = {
    "Sous-titres par Amara.org",
    "Merci de votre écoute",
    "Merci d'avoir regardé",
    ... (liste fixe)
}
```

### Problèmes
1. Liste fixe insuffisante → nouvelles hallucinations non détectées
2. Pas de score de confiance post-transcription
3. Pas de vérification factuelle IA avant action

### Recommandations
- ✅ Ajouter modèle ML de confiance transcription
- ✅ Pré-filtrer hallucinations avant envoi à LLM
- ✅ Ajouter vérification IA avant commandes critiques (domotique, suppression fichier)
- ✅ Logger toutes hallucinations détectées (amélioration continue)

---

## 🎯 Résumé des Priorités

### 🔴 CRITIQUE (Blocker Performance)
1. **Audio + Écho** → Implémenter WebRtcVad + AEC
2. **LMArena Streaming** → Débloquer réflexion profonde rapide
3. **Hallucinations** → Ajouter filtrage IA intelligent

### 🟡 IMPORTANT (Expérience Utilisateur)
1. **Caméras réseau** → Multi-device autonome
2. **Multi-utilisateurs** → Activer par défaut
3. **Performance** → Réduire latence à < 2s

### 🟢 NICE-TO-HAVE (Cosmétique)
1. **Reconn. faciale avancée** → Analyse humeur
2. **Morphes polymorphes** → Optimiser GPU
3. **Traducteur live** → Implémenter SSE

---

## ✅ Prochaines Étapes

1. **Immédiatement** : Créer modules critiques (audio, caméras réseau)
2. **Phase 2** : Optimiser LMArena et streaming
3. **Phase 3** : Améliorer UX (biométrie, performance)
4. **Phase 4** : Cosmétique (morphes, animations)

---

**Généré:** 26 avril 2026  
**Pour:** Floriace  
**Par:** PHOEBUS Diagnostic System
