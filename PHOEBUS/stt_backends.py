"""Back-ends de reconnaissance vocale (STT) de PHOEBUS."""

from dataclasses import dataclass
import importlib.util
import json
import os
import tempfile
import time

# ── Désactivation des avertissements Hugging Face (Alternative au token) ──
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_OFFLINE"] = "0"  # Mettre à 1 une fois les modèles téléchargés

from PHOEBUS.config import BASE_DIR, sr, groq_client
from PHOEBUS.runtime_resources import choose_placement

PHOEBUS_STT_BACKEND = os.getenv("PHOEBUS_STT_BACKEND", "auto").strip().lower()
PHOEBUS_WHISPER_MODEL = os.getenv("PHOEBUS_WHISPER_MODEL", "base").strip()
PHOEBUS_MLX_WHISPER_MODEL = os.getenv("PHOEBUS_MLX_WHISPER_MODEL", "").strip()
PHOEBUS_STT_AUTO_ORDER = [
    item.strip().lower()
    for item in os.getenv("PHOEBUS_STT_AUTO_ORDER", "whisper,groq,google").split(",")
    if item.strip()
]
PHOEBUS_STT_VERIFY = os.getenv("PHOEBUS_STT_VERIFY", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PHOEBUS_STT_VERIFY_BACKENDS = [
    item.strip().lower()
    for item in os.getenv("PHOEBUS_STT_VERIFY_BACKENDS", "google,whisper").split(",")
    if item.strip()
]
PHOEBUS_STT_LOG = os.getenv("PHOEBUS_STT_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
PHOEBUS_STT_DEBUG = os.getenv("PHOEBUS_STT_DEBUG", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
    """Whisper local via faster-whisper avec filtrage de silence."""
    try:
        from faster_whisper import WhisperModel
        import numpy as np

        plan = choose_placement("stt")
        device = os.getenv("PHOEBUS_WHISPER_DEVICE", plan.device).strip() or "auto"
        compute_type = (
            os.getenv("PHOEBUS_WHISPER_COMPUTE_TYPE", plan.compute_type).strip() or "auto"
        )
        if device in {"mps", "metal"}:
            device = "auto"
        model = WhisperModel(PHOEBUS_WHISPER_MODEL, device=device, compute_type=compute_type)
        print(
            f"[STT] faster-whisper chargé ({PHOEBUS_WHISPER_MODEL}, "
            f"device={device}, compute={compute_type})"
        )

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
                vad_parameters=dict(min_silence_duration_ms=500),
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


def _mlx_model_name() -> str:
    if PHOEBUS_MLX_WHISPER_MODEL:
        return PHOEBUS_MLX_WHISPER_MODEL
    if "/" in PHOEBUS_WHISPER_MODEL:
        return PHOEBUS_WHISPER_MODEL
    return f"mlx-community/whisper-{PHOEBUS_WHISPER_MODEL}"


def _try_mlx_whisper():
    """Whisper MLX pour Apple Silicon, si `mlx-whisper` est installe."""
    try:
        import mlx_whisper
        import numpy as np

        model_name = _mlx_model_name()
        print(f"[STT] mlx-whisper prêt ({model_name})")

        def recognize(audio_data):
            wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
            audio_array = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if np.max(np.abs(audio_array)) < 0.02:
                return ""

            tmp = tempfile.NamedTemporaryFile(
                mode="wb", suffix=".wav", prefix="phoebus_stt_", delete=False, dir="/tmp"
            )
            try:
                tmp.write(wav_bytes)
                tmp.flush()
                tmp.close()
                result = mlx_whisper.transcribe(
                    tmp.name,
                    path_or_hf_repo=model_name,
                    language="fr",
                )
                return str((result or {}).get("text") or "").strip()
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass

        return recognize
    except Exception as e:
        print(f"[STT] MLX-Whisper indisponible : {e}")
        return None


def _whisper_recognize_factory():
    plan = choose_placement("stt")
    if plan.backend == "mlx-whisper":
        fn = _try_mlx_whisper()
        if fn:
            return fn
    return _try_faster_whisper()


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
                response_format="text",
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
        fn = _whisper_recognize_factory()
    elif name in {"mlx", "mlx-whisper", "mlx_whisper"}:
        fn = _try_mlx_whisper()
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
        for backend in PHOEBUS_STT_AUTO_ORDER:
            fn = _factory_for(backend)
            if fn:
                name = "whisper" if backend in {"mlx", "mlx-whisper", "mlx_whisper"} else backend
                break

    _backend_cache = (name, fn)
    return _backend_cache


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def stt_status() -> dict:
    """Snapshot leger, sans charger les modeles Whisper."""
    plan = choose_placement("stt")
    available = {
        "groq": bool(groq_client),
        "google": sr is not None,
        "whisper": _module_available("faster_whisper") or _module_available("mlx_whisper"),
        "mlx_whisper": _module_available("mlx_whisper"),
        "faster_whisper": _module_available("faster_whisper"),
    }
    return {
        "requested": PHOEBUS_STT_BACKEND,
        "auto_order": PHOEBUS_STT_AUTO_ORDER,
        "whisper_model": PHOEBUS_WHISPER_MODEL,
        "mlx_whisper_model": _mlx_model_name(),
        "placement": {
            "device": plan.device,
            "backend": plan.backend,
            "compute_type": plan.compute_type,
            "reason": plan.reason,
        },
        "available": available,
    }


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
    if len(words) <= 5 and words.intersection(
        {
            "heure",
            "date",
            "météo",
            "meteo",
            "temps",
            "jour",
            "journée",
            "journee",
            "demain",
        }
    ):
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

    if any(
        marker in t
        for marker in ("météo", "meteo", "quel temps", "le temps", "prévision", "prevision")
    ):
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
                {"backend": c.backend, "text": c.text, "intent": c.intent} for c in candidates
            ],
            "selected": {
                "backend": selected.backend,
                "text": selected.text,
                "intent": selected.intent,
            },
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

    candidates.append(
        SttCandidate(primary_name or "primary", primary_text, _intent_name(primary_text))
    )

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
        print(
            f"[STT] Correction {primary_name} → {selected.backend} : {primary_text!r} → {selected.text!r}"
        )
    return selected.text
