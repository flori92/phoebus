# jarvis/wake_word.py
"""
Détection de Wake Word pour JARVIS — "Hey Jarvis" — 100% gratuit, 100% local.

Cascade (du meilleur au plus léger, tout open-source) :
  1. OpenWakeWord   MIT      — modèles ONNX pré-entraînés "hey_jarvis"
                              pip install openwakeword onnxruntime
  2. Vosk           Apache2  — STT offline ultra-précis avec keyword spotting
                              pip install vosk
                              + télécharger le modèle FR : voir commentaire ci-bas
  3. Pocketsphinx   BSD      — léger, hors ligne, zero config
                              pip install pocketsphinx
  4. Fallback STT   —        — Google/Whisper sur clips courts (déjà installé)

Aucune clé API. Aucun compte. Aucun coût mensuel.

Le module expose :
  - start(callback)   → démarre dans un thread daemon
  - stop()            → arrête proprement
  - is_running()      → bool

`callback()` est appelé sans argument à chaque déclenchement confirmé.
Code appelant → utiliser asyncio.run_coroutine_threadsafe si besoin.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Modèle Vosk FR (recommandé pour option 2) :
  curl -LO https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
  unzip vosk-model-small-fr-0.22.zip
  # Puis dans .env :
  JARVIS_VOSK_MODEL_PATH=/chemin/vers/vosk-model-small-fr-0.22
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import time
import threading
import logging
from pathlib import Path

logger = logging.getLogger("jarvis.wake_word")

# Répertoire racine du projet (pour résoudre les chemins relatifs)
_ROOT = Path(__file__).resolve().parents[1]

# ── Configuration ───────────────────────────────────────────────────────────────

# OpenWakeWord : seuil de confiance (0.0–1.0)
OWW_THRESHOLD     = float(os.getenv("JARVIS_OWW_THRESHOLD", "0.5"))
# Cooldown minimum entre deux déclenchements (secondes)
WAKE_COOLDOWN_S   = float(os.getenv("JARVIS_WAKE_COOLDOWN", "2.0"))
# Chunk audio OWW (80 ms @ 16 kHz)
OWW_CHUNK_SAMPLES = 1280
OWW_SAMPLE_RATE   = 16000

def _resolve_vosk_path() -> str:
    """Résout le chemin du modèle Vosk : absolu ou relatif à la racine du projet.
    Fonctionne sur Windows (C:\\...), macOS (/Users/...) et Linux (/home/...).
    """
    raw = os.getenv("JARVIS_VOSK_MODEL_PATH", "").strip()
    if not raw:
        # Cherche automatiquement dans models/ si non configuré
        default = _ROOT / "models" / "vosk-model-small-fr-0.22"
        if default.is_dir():
            return str(default)
        return ""
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    # Chemin relatif → résoudre depuis la racine du projet
    resolved = _ROOT / p
    return str(resolved)

VOSK_MODEL_PATH = _resolve_vosk_path()

# Vosk : mots-clés à détecter (en minuscules, adaptés à la phonétique FR)
VOSK_KEYWORDS     = [
    "jarvis", "hey jarvis", "ok jarvis", "je suis jarvis",
]

# Pocketsphinx : mots-clés avec seuil de détection (format "mot /seuil/")
PSX_KEYWORDS      = [
    "jarvis /1e-10/",
    "hey jarvis /1e-15/",
]

# Fallback STT : mots phonétiquement proches acceptés
WAKE_WORDS_PHONETIC = [
    "jarvis", "jarv", "service", "charvis", "darvis", "j'arrive",
    "hey jarvis", "ok jarvis", "yo jarvis",
]

# ── État interne ──────────────────────────────────────────────────────────────

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_callback = None
_last_trigger_ts = 0.0


def _can_trigger() -> bool:
    global _last_trigger_ts
    now = time.time()
    if now - _last_trigger_ts < WAKE_COOLDOWN_S:
        return False
    _last_trigger_ts = now
    return True


def _fire():
    """Déclenche le callback si le cooldown est respecté."""
    if _can_trigger() and _callback:
        _callback()


# ── Backend 1 : OpenWakeWord (recommandé) ────────────────────────────────────

def _try_oww() -> bool:
    """
    OpenWakeWord — MIT license, 100% local.
    Modèles ONNX pré-entraînés inclus (hey_jarvis, alexa, hey_mycroft…).
    Installation : pip install openwakeword onnxruntime

    Retourne True si la boucle a démarré et tourne jusqu'à l'arrêt.
    Retourne False si le module n'est pas disponible.
    """
    try:
        import openwakeword
        from openwakeword.model import Model as OWWModel
        import numpy as np
        import pyaudio
    except ImportError:
        logger.info("[WAKE] OpenWakeWord non installé (pip install openwakeword onnxruntime).")
        return False

    # Téléchargement automatique des modèles si absents (~5 Mo, une seule fois)
    try:
        openwakeword.utils.download_models()
    except Exception:
        pass

    # Essai avec le modèle "hey_jarvis" dédié, fallback générique
    oww = None
    for model_name in (["hey_jarvis"], None):
        try:
            kwargs = {"inference_framework": "onnx"}
            if model_name:
                kwargs["wakeword_models"] = model_name
            oww = OWWModel(**kwargs)
            break
        except Exception as e:
            logger.debug(f"[WAKE] OWW modèle {model_name} : {e}")

    if oww is None:
        logger.warning("[WAKE] OpenWakeWord : aucun modèle chargeable.")
        return False

    logger.info("[WAKE] ✅ OpenWakeWord actif (gratuit, local, MIT).")

    p = pyaudio.PyAudio()
    stream = p.open(
        rate=OWW_SAMPLE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=OWW_CHUNK_SAMPLES,
    )

    try:
        while not _stop_event.is_set():
            try:
                raw = stream.read(OWW_CHUNK_SAMPLES, exception_on_overflow=False)
                audio_np = np.frombuffer(raw, dtype=np.int16)
                prediction = oww.predict(audio_np)
                for score in prediction.values():
                    if score >= OWW_THRESHOLD:
                        logger.info(f"[WAKE] OWW : wake word ! (score={score:.2f})")
                        _fire()
            except Exception as e:
                logger.debug(f"[WAKE] OWW chunk error : {e}")
                time.sleep(0.05)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    return True


# ── Backend 2 : Vosk (Apache 2.0) ────────────────────────────────────────────

def _try_vosk() -> bool:
    """
    Vosk — Apache 2.0 license, 100% gratuit, 100% hors ligne.
    STT embarqué avec grammaire restreinte pour le keyword spotting.
    Installation : pip install vosk
    Modèle FR (~40 Mo) : https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip

    Sans modèle configuré, Vosk tente un modèle EN si aucun modèle FR n'est trouvé.
    Retourne True si la boucle démarre.
    """
    try:
        from vosk import Model, KaldiRecognizer
        import pyaudio
        import json as _json
    except ImportError:
        logger.info("[WAKE] Vosk non installé (pip install vosk).")
        return False

    # Chargement du modèle
    model_path = VOSK_MODEL_PATH
    if model_path and not os.path.isdir(model_path):
        logger.warning(f"[WAKE] Vosk : chemin modèle introuvable → {model_path}")
        model_path = ""

    try:
        if model_path:
            model = Model(model_path)
        else:
            # Vosk télécharge automatiquement un petit modèle si aucun n'est trouvé
            model = Model(lang="fr")
    except Exception as e:
        logger.warning(f"[WAKE] Vosk : impossible de charger le modèle : {e}")
        return False

    # Grammaire restreinte = ultra rapide + peu de faux positifs
    grammar = _json.dumps(VOSK_KEYWORDS + ["[unk]"])
    try:
        rec = KaldiRecognizer(model, OWW_SAMPLE_RATE, grammar)
    except Exception:
        rec = KaldiRecognizer(model, OWW_SAMPLE_RATE)

    logger.info("[WAKE] ✅ Vosk actif (gratuit, Apache 2.0, hors ligne).")

    p = pyaudio.PyAudio()
    stream = p.open(
        rate=OWW_SAMPLE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=4096,
    )

    try:
        while not _stop_event.is_set():
            try:
                raw = stream.read(4096, exception_on_overflow=False)
                if rec.AcceptWaveform(raw):
                    result = _json.loads(rec.Result())
                    texte = result.get("text", "").lower().strip()
                    if texte and any(kw in texte for kw in VOSK_KEYWORDS):
                        logger.info(f"[WAKE] Vosk : wake word détecté → '{texte}'")
                        _fire()
                else:
                    # Résultat partiel — peut déclencher sur un fragment clair
                    partial = _json.loads(rec.PartialResult())
                    texte_p = partial.get("partial", "").lower().strip()
                    if texte_p in ("jarvis", "hey jarvis"):
                        logger.info(f"[WAKE] Vosk partial : '{texte_p}'")
                        _fire()
            except Exception as e:
                logger.debug(f"[WAKE] Vosk chunk error : {e}")
                time.sleep(0.05)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    return True


# ── Backend 3 : Pocketsphinx (BSD) ───────────────────────────────────────────

def _try_pocketsphinx() -> bool:
    """
    Pocketsphinx — BSD license, 100% gratuit, ultra-léger (< 1 Mo).
    Mode "keyword spotting" : idéal pour les wake words, très faible CPU.
    Installation : pip install pocketsphinx

    Retourne True si la boucle démarre.
    """
    try:
        from pocketsphinx import LiveSpeech, get_model_path
    except ImportError:
        logger.info("[WAKE] Pocketsphinx non installé (pip install pocketsphinx).")
        return False

    logger.info("[WAKE] ✅ Pocketsphinx actif (gratuit, BSD, ultra-léger).")

    try:
        speech = LiveSpeech(
            sampling_rate=OWW_SAMPLE_RATE,
            kws="; ".join(PSX_KEYWORDS),  # format "mot /seuil/; mot2 /seuil2/"
        )
        for phrase in speech:
            if _stop_event.is_set():
                break
            texte = str(phrase).lower().strip()
            if texte and any(kw.split(" /")[0] in texte for kw in PSX_KEYWORDS):
                logger.info(f"[WAKE] Pocketsphinx : wake word → '{texte}'")
                _fire()
    except Exception as e:
        logger.warning(f"[WAKE] Pocketsphinx erreur : {e}")
        return False

    return True


# ── Backend 4 : Fallback STT phonétique ──────────────────────────────────────

def _run_fallback_stt():
    """
    Dernier recours : écoute de clips courts (2s) transcrit par le backend STT
    existant (Google ou faster-whisper — déjà installés).
    Déclenche si un mot-clé phonétique est détecté.
    Pas de dépendance extra — tout est déjà là.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        logger.error("[WAKE] SpeechRecognition absent — aucun backend wake word fonctionnel.")
        return

    from jarvis.stt_backends import get_backend
    stt_name, stt_fn = get_backend()
    if not stt_fn:
        logger.error("[WAKE] Fallback STT : aucun backend STT disponible.")
        return

    logger.info(f"[WAKE] ⚠️  Fallback STT actif (backend: {stt_name}) — moins précis, mais fonctionnel.")
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = 300
    recognizer.pause_threshold = 0.6

    try:
        with sr.Microphone(sample_rate=16000) as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            while not _stop_event.is_set():
                try:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=2.5)
                    try:
                        texte = (stt_fn(audio) or "").lower().strip()
                    except Exception:
                        continue
                    if any(w in texte for w in WAKE_WORDS_PHONETIC):
                        logger.info(f"[WAKE] Fallback STT : wake word dans '{texte}'")
                        _fire()
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    logger.debug(f"[WAKE] Fallback STT error : {e}")
                    time.sleep(1)
    except Exception as e:
        logger.error(f"[WAKE] Impossible d'ouvrir le micro : {e}")


# ── Sélection du backend actif ────────────────────────────────────────────────

def _run():
    """Essaie les backends dans l'ordre, s'arrête au premier fonctionnel."""
    _stop_event.clear()

    backend = os.getenv("JARVIS_WAKE_BACKEND", "auto").strip().lower()

    if backend == "oww" or backend == "auto":
        if _try_oww():
            return

    if backend == "vosk" or backend == "auto":
        if _try_vosk():
            return

    if backend == "pocketsphinx" or backend == "auto":
        if _try_pocketsphinx():
            return

    if backend in ("stt", "auto"):
        _run_fallback_stt()


# ── API publique ──────────────────────────────────────────────────────────────

def start(callback):
    """Démarre la détection wake word dans un thread daemon.

    `callback` sera appelé sans argument à chaque déclenchement.
    Ordre d'essai : OWW → Vosk → Pocketsphinx → Fallback STT.
    Forcer un backend : JARVIS_WAKE_BACKEND=oww|vosk|pocketsphinx|stt dans .env
    """
    global _thread, _callback
    _callback = callback
    _stop_event.clear()
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, daemon=True, name="JarvisWakeWord")
    _thread.start()
    logger.info("[WAKE] Thread wake word démarré.")


def stop():
    """Arrête proprement le thread de détection."""
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=3)
    logger.info("[WAKE] Thread wake word arrêté.")


def is_running() -> bool:
    return bool(_thread and _thread.is_alive())
