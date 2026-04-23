"""Back-ends de synthèse vocale (TTS) de JARVIS.

Un back-end renvoie un fichier MP3 à partir d'un texte. Le code appelant
(`voice.parler`) se charge ensuite de lire le fichier côté PC ou de
l'envoyer aux clients WebSocket.

Sélection automatique : si `ELEVEN_API_KEY` est défini → ElevenLabs,
sinon Edge-TTS (par défaut). La fonction `synthesize_to_file` lève
`TtsUnavailable` si aucun back-end n'est disponible.
"""
import os
import requests

from jarvis.config import edge_tts


ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "").strip()
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "ErXwobaYiN019PkySvjV").strip()  # Antoni par défaut
ELEVEN_MODEL = os.getenv("ELEVEN_MODEL", "eleven_multilingual_v2").strip()
JARVIS_TTS_BACKEND = os.getenv("JARVIS_TTS_BACKEND", "auto").strip().lower()  # auto | edge | eleven


class TtsUnavailable(Exception):
    pass


def _backend_actif() -> str:
    if JARVIS_TTS_BACKEND == "eleven":
        return "eleven"
    if JARVIS_TTS_BACKEND == "edge":
        return "edge"
    # auto
    if ELEVEN_API_KEY:
        return "eleven"
    if edge_tts is not None:
        return "edge"
    return "none"


async def _synth_edge(texte: str, out_path: str) -> None:
    if edge_tts is None:
        raise TtsUnavailable("edge_tts non installé")
    communicate = edge_tts.Communicate(texte, voice="fr-FR-HenriNeural")
    await communicate.save(out_path)


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


async def synthesize_to_file(texte: str, out_path: str) -> str:
    """Synthétise `texte` dans le fichier `out_path`. Renvoie le nom du
    back-end utilisé. Essaie ElevenLabs puis retombe sur Edge-TTS."""
    backend = _backend_actif()
    if backend == "none":
        raise TtsUnavailable("Aucun back-end TTS disponible (ni ElevenLabs ni edge_tts).")

    if backend == "eleven":
        try:
            import asyncio
            await asyncio.to_thread(_synth_eleven_sync, texte, out_path)
            return "eleven"
        except Exception as e:
            print(f"[TTS] ElevenLabs indisponible ({e}), repli Edge-TTS.")
            backend = "edge"

    if backend == "edge":
        await _synth_edge(texte, out_path)
        return "edge"

    raise TtsUnavailable("Aucun back-end TTS opérationnel.")
