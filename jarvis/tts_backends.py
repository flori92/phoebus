"""Back-ends de synthèse vocale (TTS) de JARVIS.

Chaque back-end sait produire un fichier audio à partir d'un texte. Le code
appelant (`voice.parler`) lit ensuite le fichier en local (pygame) ou
l'envoie aux clients WebSocket en base64.

Quatre back-ends supportés, sélectionnables via `JARVIS_TTS_BACKEND` :

- `piper`    → Piper neural TTS local (offline, gratuit, rapide sur CPU).
               Nécessite `pip install piper-tts` et un fichier modèle ONNX.
- `eleven`   → ElevenLabs (payant, ultra-naturel).
- `edge`     → Edge-TTS (Microsoft, non officiel, gratuit).
               Voix par défaut : `fr-FR-RemyMultilingualNeural` — plus chaleureuse
               que l'ancien Henri, avec léger ajustement de rate/pitch pour
               sortir du ton plat.
- `auto`     → Piper si un modèle est configuré, sinon ElevenLabs si clé,
               sinon Edge-TTS.

Le format de sortie peut être WAV (Piper) ou MP3 (Eleven, Edge). Le fichier
conserve l'extension fournie par le code appelant — pygame et les clients
Web détectent le format via le magic number, donc c'est transparent.
"""
import os
import asyncio
import subprocess
import wave

import requests

from jarvis.config import edge_tts
from jarvis.lipsync import build_lipsync_frames_from_word_boundaries


# ── Configuration Edge-TTS ─────────────────────────────────────────────────
# Voix multilingue plus chaleureuse que HenriNeural. Peut être surchargée.
EDGE_VOICE = os.getenv("EDGE_VOICE", "fr-FR-RemyMultilingualNeural").strip()
EDGE_RATE = os.getenv("EDGE_RATE", "+4%").strip()     # +4% : sort du débit monotone
EDGE_PITCH = os.getenv("EDGE_PITCH", "-2Hz").strip()  # -2Hz : légèrement plus grave, plus posé
EDGE_VOLUME = os.getenv("EDGE_VOLUME", "+0%").strip()

# ── Configuration ElevenLabs ──────────────────────────────────────────────
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "").strip()
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "ErXwobaYiN019PkySvjV").strip()  # Antoni
ELEVEN_MODEL = os.getenv("ELEVEN_MODEL", "eleven_multilingual_v2").strip()

# ── Configuration Piper ───────────────────────────────────────────────────
# Modèle .onnx : téléchargeable sur https://huggingface.co/rhasspy/piper-voices
# Exemples FR : fr_FR-siwis-medium.onnx (~60 Mo, bonne qualité).
PIPER_MODEL = os.getenv("JARVIS_PIPER_MODEL", "").strip()
PIPER_CONFIG = os.getenv("JARVIS_PIPER_CONFIG", "").strip()
# Débit Piper : 1.0 = normal ; >1.0 = plus lent (inverse de edge-tts).
PIPER_LENGTH_SCALE = float(os.getenv("JARVIS_PIPER_LENGTH", "0.95"))
PIPER_NOISE_SCALE = float(os.getenv("JARVIS_PIPER_NOISE", "0.667"))
PIPER_NOISE_W = float(os.getenv("JARVIS_PIPER_NOISE_W", "0.8"))

JARVIS_TTS_BACKEND = os.getenv("JARVIS_TTS_BACKEND", "auto").strip().lower()


class TtsUnavailable(Exception):
    pass


# ── Détection des back-ends disponibles ────────────────────────────────────

_piper_voice = None
_piper_checked = False


def _piper_available():
    """Charge paresseusement la voix Piper. Renvoie l'instance ou None."""
    global _piper_voice, _piper_checked
    if _piper_checked:
        return _piper_voice
    _piper_checked = True

    if not PIPER_MODEL or not os.path.exists(PIPER_MODEL):
        return None
    try:
        from piper.voice import PiperVoice
        config = PIPER_CONFIG or (PIPER_MODEL + ".json")
        config = config if os.path.exists(config) else None
        _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=config, use_cuda=False)
        print(f"[TTS] Piper chargé : {os.path.basename(PIPER_MODEL)}")
        return _piper_voice
    except Exception as e:
        print(f"[TTS] Piper module absent ou erreur de chargement : {e}")
        _piper_voice = None
        return None


def _piper_cli_available():
    """Vrai si le binaire `piper` est dans le PATH (fallback subprocess)."""
    if not PIPER_MODEL or not os.path.exists(PIPER_MODEL):
        return False
    try:
        r = subprocess.run(["piper", "--help"], capture_output=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def _backend_actif() -> str:
    if JARVIS_TTS_BACKEND == "piper":
        return "piper"
    if JARVIS_TTS_BACKEND == "eleven":
        return "eleven"
    if JARVIS_TTS_BACKEND == "edge":
        return "edge"

    # auto : local gratuit d'abord
    if _piper_available() is not None or _piper_cli_available():
        return "piper"
    if ELEVEN_API_KEY:
        return "eleven"
    if edge_tts is not None:
        return "edge"
    return "none"


# ── Back-ends ──────────────────────────────────────────────────────────────

async def _synth_edge(texte: str, out_path: str) -> dict:
    if edge_tts is None:
        raise TtsUnavailable("edge_tts non installé")
    communicate = edge_tts.Communicate(
        texte,
        voice=EDGE_VOICE,
        rate=EDGE_RATE,
        pitch=EDGE_PITCH,
        volume=EDGE_VOLUME,
        boundary="WordBoundary",
    )
    audio_chunks = []
    boundaries = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            boundaries.append(
                {
                    "offset_ms": round(float(chunk["offset"]) / 10000.0, 1),
                    "duration_ms": round(float(chunk["duration"]) / 10000.0, 1),
                    "text": chunk.get("text", ""),
                }
            )

    if not audio_chunks:
        raise TtsUnavailable("Aucun audio recu depuis edge-tts")

    with open(out_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    result = {"backend": "edge"}
    frames = build_lipsync_frames_from_word_boundaries(boundaries)
    if frames:
        result["lipsync"] = {
            "source": "edge_word_boundaries",
            "frames": frames,
            "duration_ms": round(
                frames[-1]["time_ms"] + frames[-1]["duration_ms"], 1
            ),
        }
    return result


def _synth_eleven_sync(texte: str, out_path: str) -> None:
    if not ELEVEN_API_KEY:
        raise TtsUnavailable("ELEVEN_API_KEY manquante")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": texte,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.85,
            "style": 0.35,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise TtsUnavailable(f"ElevenLabs HTTP {resp.status_code} : {resp.text[:120]}")
    with open(out_path, "wb") as f:
        f.write(resp.content)


def _synth_piper_sync(texte: str, out_path: str) -> None:
    """Synthétise avec Piper via l'API Python si dispo, sinon en subprocess."""
    voice = _piper_available()
    if voice is not None:
        # Piper écrit du WAV natif 22 kHz — parfait pour pygame & navigateur.
        with wave.open(out_path, "wb") as wav:
            voice.synthesize(
                texte,
                wav,
                length_scale=PIPER_LENGTH_SCALE,
                noise_scale=PIPER_NOISE_SCALE,
                noise_w=PIPER_NOISE_W,
            )
        return

    # Fallback CLI : `piper --model ... --output_file ...` lit le texte sur stdin.
    if not _piper_cli_available():
        raise TtsUnavailable("Piper indisponible (ni module ni CLI).")
    try:
        cmd = [
            "piper",
            "--model", PIPER_MODEL,
            "--output_file", out_path,
            "--length_scale", str(PIPER_LENGTH_SCALE),
            "--noise_scale", str(PIPER_NOISE_SCALE),
            "--noise_w", str(PIPER_NOISE_W),
        ]
        if PIPER_CONFIG:
            cmd += ["--config", PIPER_CONFIG]
        res = subprocess.run(cmd, input=texte.encode("utf-8"),
                             capture_output=True, timeout=30)
        if res.returncode != 0:
            raise TtsUnavailable(f"Piper CLI erreur : {res.stderr.decode(errors='ignore')[:200]}")
    except FileNotFoundError:
        raise TtsUnavailable("Binaire `piper` introuvable dans le PATH.")


# ── Point d'entrée ─────────────────────────────────────────────────────────

async def synthesize_to_file(texte: str, out_path: str) -> dict:
    """Synthétise `texte` dans `out_path`.

    Chaîne de repli : priorité au back-end configuré, repli sur Edge-TTS.
    """
    backend = _backend_actif()
    if backend == "none":
        raise TtsUnavailable("Aucun back-end TTS disponible (ni Piper, ni ElevenLabs, ni edge_tts).")

    if backend == "piper":
        try:
            await asyncio.to_thread(_synth_piper_sync, texte, out_path)
            return {"backend": "piper"}
        except Exception as e:
            print(f"[TTS] Piper indisponible ({e}), repli.")
            backend = "eleven" if ELEVEN_API_KEY else "edge"

    if backend == "eleven":
        try:
            await asyncio.to_thread(_synth_eleven_sync, texte, out_path)
            return {"backend": "eleven"}
        except Exception as e:
            print(f"[TTS] ElevenLabs indisponible ({e}), repli Edge-TTS.")
            backend = "edge"

    if backend == "edge":
        return await _synth_edge(texte, out_path)

    raise TtsUnavailable("Aucun back-end TTS opérationnel.")
