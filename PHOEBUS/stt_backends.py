"""Back-ends de reconnaissance vocale (STT) de PHOEBUS."""
from dataclasses import dataclass
import json
import os
import time

# ── Désactivation des avertissements Hugging Face (Alternative au token) ──
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_OFFLINE"] = "0" # Mettre à 1 une fois les modèles téléchargés

from PHOEBUS.config import BASE_DIR, sr, groq_client


PHOEBUS_STT_BACKEND = os.getenv("PHOEBUS_STT_BACKEND", "auto").strip().lower()  # auto | groq | google | whisper
PHOEBUS_WHISPER_MODEL = os.getenv("PHOEBUS_WHISPER_MODEL", "base").strip()
PHOEBUS_STT_VERIFY = os.getenv("PHOEBUS_STT_VERIFY", "1").strip().lower() in {"1", "true", "yes", "on"}
PHOEBUS_STT_VERIFY_BACKENDS = [
    item.strip().lower()
    for item in os.getenv("PHOEBUS_STT_VERIFY_BACKENDS", "google,whisper").split(",")
    if item.strip()
]
PHOEBUS_STT_LOG = os.getenv("PHOEBUS_STT_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
PHOEBUS_STT_DEBUG = os.getenv("PHOEBUS_STT_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
try:
    PHOEBUS_STT_API_TIMEOUT = float(os.getenv("PHOEBUS_STT_API_TIMEOUT", "8"))
except ValueError:
    PHOEBUS_STT_API_TIMEOUT = 8.0


_backend_cache = None
_factory_cache = {}


@dataclass(frozen=True)
class SttCandidate:
    backend: str
    text: str
    intent: str = ""


def _try_faster_whisper():
    """Version ultra-rapide optimisée pour Apple Silicon (M1/M2/M3) avec filtrage de silence."""
    try:
        from faster_whisper import WhisperModel
        import numpy as np
        # Modèle 'small' ou 'distil-large-v3' pour le meilleur compromis vitesse/précision
        model = WhisperModel(PHOEBUS_WHISPER_MODEL, device="auto", compute_type="auto")

        def recognize(audio_data):
            # ── VAD Logic (Voice Activity Detection) ──
            # On vérifie l'énergie pour ignorer le silence et éviter les hallucinations
            wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
            audio_array = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Si le signal est trop faible, on ne tente même pas la transcription
            if np.max(np.abs(audio_array)) < 0.02: 
                return ""

            import io
            audio_file = io.BytesIO(wav_bytes)
            
            # vad_filter=True est essentiel pour bloquer les hallucinations de Whisper 
            # (comme "Sous-titres par Amara.org" ou "Merci de votre écoute")
            segments, info = model.transcribe(
                audio_file, 
                language="fr", 
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            text = " ".join(seg.text for seg in segments).strip()
            
            # Filtre de confiance additionnel pour éviter le bruit
            if info.language_probability < 0.6:
                return ""

            return text

        return recognize
    except Exception as e:
        print(f"[STT] Faster-Whisper indisponible : {e}")
        return None


def _google_recognize_factory():
    if sr is None:
        return None
    r = sr.Recognizer()

    def recognize(audio_data):
        return r.recognize_google(audio_data, language="fr-FR")

    return recognize


def _groq_recognize_factory():
    if not groq_client:
        return None

    import tempfile
    import numpy as np
    import io

    def recognize(audio_data):
        # ── VAD Logic local pour Groq ──
        # On s'assure d'avoir du 16kHz pour le calcul d'énergie
        wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
        audio_array = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Seuil d'énergie pour ignorer le silence (Whisper hallucine sur le silence)
        energy = np.max(np.abs(audio_array))
        if energy < 0.04: 
            return ""

        # On utilise le format original pour l'envoi à l'API (plus haute qualité possible)
        api_wav = audio_data.get_wav_data()
        
        try:
            client = groq_client.with_options(timeout=PHOEBUS_STT_API_TIMEOUT)
            # Groq API demande un tuple (nom_fichier, bytes) ou un file-like object
            transcription = client.audio.transcriptions.create(
                file=("input.wav", api_wav),
                model="whisper-large-v3",
                language="fr",
                prompt="PHOEBUS, assistant vocal d'élite. Bonjour Floriace.",
                response_format="text"
            )
            return transcription.strip()
        except Exception as e:
            print(f"[STT] Erreur Groq : {e}")
            return ""

    return recognize


def _factory_for(name: str):
    name = (name or "").strip().lower()
    if name in _factory_cache:
        return _factory_cache[name]

    if name == "groq":
        fn = _groq_recognize_factory()
    elif name == "whisper":
        fn = _try_faster_whisper()
    elif name == "google":
        fn = _google_recognize_factory()
    else:
        fn = None

    _factory_cache[name] = fn
    return fn


def get_backend():
    """Renvoie (nom, fonction recognize). None si rien de disponible."""
    global _backend_cache
    if _backend_cache is not None:
        return _backend_cache

    name = None
    fn = None

    if PHOEBUS_STT_BACKEND == "groq":
        fn = _factory_for("groq")
        name = "groq" if fn else None
    elif PHOEBUS_STT_BACKEND == "whisper":
        fn = _factory_for("whisper")
        name = "whisper" if fn else None
    elif PHOEBUS_STT_BACKEND == "google":
        fn = _factory_for("google")
        name = "google" if fn else None
    else:  # auto
        # Ordre de préférence : groq (si clé dispo) -> faster-whisper (si installé) -> google
        fn = _factory_for("groq")
        if fn:
            name = "groq"
        else:
            fn = _factory_for("whisper")
            if fn:
                name = "whisper"
            else:
                fn = _factory_for("google")
                name = "google" if fn else None

    _backend_cache = (name, fn)
    return _backend_cache


def _intent_name(text: str) -> str:
    try:
        from PHOEBUS.intent import detect
        intent = detect(text)
        return intent.name if intent else ""
    except Exception:
        return ""


def _should_verify(text: str) -> bool:
    if not PHOEBUS_STT_VERIFY:
        return False
    if not text:
        return True

    intent = _intent_name(text)
    words = {
        word.strip(".,!?;:()[]{}'\"").lower()
        for word in text.split()
        if word.strip(".,!?;:()[]{}'\"")
    }
    if intent in {"heure", "date"}:
        return True
    if len(words) <= 5 and words.intersection({
        "heure", "date", "météo", "meteo", "temps",
        "jour", "journée", "journee", "demain",
    }):
        return True
    return False


def _score_candidate(candidate: SttCandidate, primary: bool = False) -> float:
    text = (candidate.text or "").strip()
    if not text:
        return -1000

    t = text.lower()
    score = 0.0
    if primary:
        score += 10.0

    intent_weights = {
        "meteo": 70.0,
        "timer": 65.0,
        "allume": 60.0,
        "eteins": 60.0,
        "system_stats": 55.0,
        "heure": 45.0,
        "date": 45.0,
    }
    score += intent_weights.get(candidate.intent, 20.0 if candidate.intent else 0.0)

    if any(marker in t for marker in ("météo", "meteo", "quel temps", "le temps", "prévision", "prevision")):
        score += 20.0
    if any(marker in t for marker in ("heure", "quelle heure", "il est quelle heure")):
        score += 8.0
    if any(marker in t for marker in ("sous-titres", "abonnez-vous", "merci d'avoir regardé")):
        score -= 80.0

    return score + min(len(t), 80) / 100.0


def _choose_candidate(candidates: list[SttCandidate]) -> tuple[SttCandidate, str]:
    non_empty = [c for c in candidates if c.text.strip()]
    if not non_empty:
        return SttCandidate("", ""), "empty"
    if len(non_empty) == 1:
        return non_empty[0], "single"

    scored = [
        (_score_candidate(candidate, primary=(index == 0)), index, candidate)
        for index, candidate in enumerate(non_empty)
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_index, best = scored[0]
    primary = non_empty[0]
    primary_score = _score_candidate(primary, primary=True)

    if best_index != 0 and best_score >= primary_score + 8:
        return best, f"verified:{best.backend}"
    return primary, "primary"


def _log_transcription(candidates: list[SttCandidate], selected: SttCandidate, reason: str) -> None:
    if not PHOEBUS_STT_LOG:
        return
    try:
        log_path = BASE_DIR / "logs" / "voice_transcripts.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "candidates": [
                {"backend": c.backend, "text": c.text, "intent": c.intent}
                for c in candidates
            ],
            "selected": {"backend": selected.backend, "text": selected.text, "intent": selected.intent},
            "reason": reason,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recognize_with_verification(audio_data, primary=None) -> str:
    """Transcrit l'audio et vérifie les commandes courtes à fort risque de confusion.

    Cas visé : le STT principal entend "quelle heure" alors que l'utilisateur a dit
    "météo de la journée". On interroge alors un second back-end et on choisit la
    transcription qui correspond à l'intention la plus plausible.
    """
    primary_name, primary_fn = primary or get_backend()
    if not primary_fn:
        return ""

    candidates = []
    try:
        primary_text = (primary_fn(audio_data) or "").strip()
    except Exception as e:
        print(f"[STT] Erreur {primary_name} : {e}")
        primary_text = ""

    candidates.append(SttCandidate(primary_name or "primary", primary_text, _intent_name(primary_text)))

    if _should_verify(primary_text):
        for backend in PHOEBUS_STT_VERIFY_BACKENDS:
            if backend == primary_name:
                continue
            fn = _factory_for(backend)
            if not fn:
                continue
            try:
                text = (fn(audio_data) or "").strip()
            except Exception as e:
                if PHOEBUS_STT_DEBUG:
                    print(f"[STT] Vérification {backend} échouée : {e}")
                text = ""
            candidates.append(SttCandidate(backend, text, _intent_name(text)))

    selected, reason = _choose_candidate(candidates)
    _log_transcription(candidates, selected, reason)

    if selected.backend != (primary_name or "primary"):
        print(f"[STT] Correction {primary_name} → {selected.backend} : {primary_text!r} → {selected.text!r}")
    return selected.text
