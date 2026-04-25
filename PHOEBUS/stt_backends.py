"""Back-ends de reconnaissance vocale (STT) de PHOEBUS."""
import os

# ── Désactivation des avertissements Hugging Face (Alternative au token) ──
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_OFFLINE"] = "0" # Mettre à 1 une fois les modèles téléchargés

from PHOEBUS.config import sr, groq_client


PHOEBUS_STT_BACKEND = os.getenv("PHOEBUS_STT_BACKEND", "auto").strip().lower()  # auto | groq | google | whisper
PHOEBUS_WHISPER_MODEL = os.getenv("PHOEBUS_WHISPER_MODEL", "base").strip()


_backend_cache = None


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
    def recognize(audio_data):
        wav_bytes = audio_data.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            path = f.name
        try:
            with open(path, "rb") as file:
                # Groq API demande un tuple (nom_fichier, bytes) ou un file-like object
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(path), file.read()),
                    model="whisper-large-v3",
                    language="fr",
                    response_format="text"
                )
            return transcription.strip()
        except Exception as e:
            print(f"[STT] Erreur Groq : {e}")
            return ""
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    return recognize


def get_backend():
    """Renvoie (nom, fonction recognize). None si rien de disponible."""
    global _backend_cache
    if _backend_cache is not None:
        return _backend_cache

    name = None
    fn = None

    if PHOEBUS_STT_BACKEND == "groq":
        fn = _groq_recognize_factory()
        name = "groq" if fn else None
    elif PHOEBUS_STT_BACKEND == "whisper":
        fn = _try_faster_whisper()
        name = "whisper" if fn else None
    elif PHOEBUS_STT_BACKEND == "google":
        fn = _google_recognize_factory()
        name = "google" if fn else None
    else:  # auto
        # Ordre de préférence : groq (si clé dispo) -> faster-whisper (si installé) -> google
        fn = _groq_recognize_factory()
        if fn:
            name = "groq"
        else:
            fn = _try_faster_whisper()
            if fn:
                name = "whisper"
            else:
                fn = _google_recognize_factory()
                name = "google" if fn else None

    _backend_cache = (name, fn)
    return _backend_cache
