"""Back-ends de reconnaissance vocale (STT) de JARVIS.

Deux moteurs pour l'instant :
- `google` (défaut) via `speech_recognition.recognize_google` — rapide, cloud.
- `whisper` local via `openai-whisper` ou `faster-whisper`, activé quand la
  dépendance est installée et que `JARVIS_STT_BACKEND=whisper` (ou `auto` +
  modèle disponible). Plus robuste au bruit et aux accents, mais plus lent.

Le choix du back-end se fait une seule fois au démarrage via `get_backend()`.
"""
import os

from jarvis.config import sr, groq_client


JARVIS_STT_BACKEND = os.getenv("JARVIS_STT_BACKEND", "auto").strip().lower()  # auto | groq | google | whisper
JARVIS_WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "base").strip()


_backend_cache = None


def _try_whisper():
    """Renvoie une fonction `recognize(audio_data) -> str` ou None si indispo."""
    try:
        import tempfile
        import whisper  # openai-whisper
        model = whisper.load_model(JARVIS_WHISPER_MODEL)

        def recognize(audio_data):
            wav_bytes = audio_data.get_wav_data()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                path = f.name
            try:
                res = model.transcribe(path, language="fr", fp16=False)
                return (res.get("text") or "").strip()
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass

        return recognize
    except Exception:
        pass

    try:
        import tempfile
        from faster_whisper import WhisperModel
        fw = WhisperModel(JARVIS_WHISPER_MODEL, device="auto", compute_type="auto")

        def recognize(audio_data):
            wav_bytes = audio_data.get_wav_data()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                path = f.name
            try:
                segments, _ = fw.transcribe(path, language="fr")
                return " ".join(seg.text for seg in segments).strip()
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass

        return recognize
    except Exception:
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

    if JARVIS_STT_BACKEND == "groq":
        fn = _groq_recognize_factory()
        name = "groq" if fn else None
    elif JARVIS_STT_BACKEND == "whisper":
        fn = _try_whisper()
        name = "whisper" if fn else None
    elif JARVIS_STT_BACKEND == "google":
        fn = _google_recognize_factory()
        name = "google" if fn else None
    else:  # auto
        # Ordre de préférence : groq (si clé dispo) -> whisper (si installé) -> google
        fn = _groq_recognize_factory()
        if fn:
            name = "groq"
        else:
            fn = _try_whisper()
            if fn:
                name = "whisper"
            else:
                fn = _google_recognize_factory()
                name = "google" if fn else None

    _backend_cache = (name, fn)
    return _backend_cache
