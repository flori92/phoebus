"""Cache de synthèse vocale — "instant playback" pour les phrases fréquentes.

Motivation : la majorité des répliques de PHOEBUS sont répétitives
("Oui Monsieur.", "C'est noté.", "J'écoute."...). Synthétiser chacune à
chaque fois coûte 300–800 ms via Edge-TTS ou ElevenLabs. En les gardant
en cache disque, on passe à ~5 ms (juste lecture fichier).

Deux modes de cache :

1. **Pré-warming** : au démarrage, on synthétise ~30 phrases cibles en
   arrière-plan pour qu'elles soient prêtes dès le premier usage.
2. **Au vol** : chaque phrase synthétisée est sauvegardée. Deuxième
   occurrence = gratuite.

Clé de cache : hash (texte normalisé + voix + backend). Les fichiers
audio sont stockés sous `phoebus_tts_cache/`.

Taille plafonnée via LRU (200 entrées par défaut). La maintenance
tourne en tâche de fond côté proactive loop.
"""

import os
import hashlib
import shutil
import time
from pathlib import Path
from typing import Optional

from PHOEBUS.config import BASE_DIR
from PHOEBUS.text_shaping import naturaliser

CACHE_DIR = BASE_DIR / "phoebus_tts_cache"
CACHE_MAX_ENTRIES = 200

# Phrases pré-chauffées au démarrage. Ordre = priorité.
PREWARM_PHRASES = [
    # Acquiescements / ponctuation d'échange
    "Oui, Monsieur.",
    "Bien sûr.",
    "Tout à fait.",
    "Absolument.",
    "Pas de problème.",
    "C'est noté.",
    "J'écoute.",
    "Je vous écoute.",
    "Je vous écoute, Monsieur.",
    "Je vous écoute toujours, Monsieur.",
    "Un instant.",
    "Un instant, Monsieur.",
    "Je m'en occupe.",
    "Tout de suite.",
    "J'y réfléchis.",
    # Salutations
    "Bonjour Floriace.",
    "Bonsoir Monsieur.",
    "Ravi de vous revoir.",
    "À tout à l'heure, Monsieur.",
    "Bonne nuit, Floriace.",
    # Clarifications
    "Pardon, je n'ai pas bien compris. Vous pouvez répéter ?",
    "Dans quelle pièce, Monsieur ?",
    "Vous pouvez préciser ?",
    # Confirmations sensibles
    "Action confirmée, Floriace. J'exécute.",
    "Action annulée, Monsieur.",
    "D'accord, j'annule.",
    # Excuses
    "Désolé, j'ai eu un petit raté.",
    "Mille excuses, Floriace.",
    # Fermetures
    "Voilà qui est fait.",
    "C'est fait, Monsieur.",
]


def _ensure_dir() -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[CACHE-TTS] création dossier impossible : {e}")


def _cache_key(texte: str, voice: str, backend: str) -> str:
    norm = (texte or "").strip().lower()
    raw = f"{backend}|{voice}|{norm}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.mp3"


def lookup(texte: str, voice: str, backend: str) -> Optional[Path]:
    """Retourne le chemin du fichier en cache si présent et non vide, sinon None.

    Met à jour l'atime du fichier pour l'ordonnancement LRU.
    """
    _ensure_dir()
    key = _cache_key(naturaliser(texte), voice, backend)
    path = _cache_path(key)
    if path.exists() and path.stat().st_size > 0:
        try:
            os.utime(path, None)  # bump atime → utilisé par LRU
        except Exception:
            pass
        return path
    return None


def register(texte: str, voice: str, backend: str, src_path: str) -> None:
    """Copie `src_path` dans le cache sous la clé calculée."""
    _ensure_dir()
    key = _cache_key(naturaliser(texte), voice, backend)
    dst = _cache_path(key)
    try:
        if not os.path.exists(src_path) or os.path.getsize(src_path) == 0:
            return
        shutil.copyfile(src_path, dst)
    except Exception as e:
        print(f"[CACHE-TTS] erreur register : {e}")


def prune(max_entries: int = CACHE_MAX_ENTRIES) -> int:
    """Enlève les fichiers les plus vieux si on dépasse `max_entries`.

    Renvoie le nombre de fichiers supprimés. Basé sur l'atime (LRU).
    """
    _ensure_dir()
    try:
        files = [(p, p.stat().st_atime) for p in CACHE_DIR.glob("*.mp3") if p.is_file()]
    except Exception:
        return 0
    if len(files) <= max_entries:
        return 0
    files.sort(key=lambda t: t[1])  # plus vieux d'abord
    removed = 0
    for path, _ in files[: len(files) - max_entries]:
        try:
            path.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def status() -> dict:
    """Retourne un snapshot du cache TTS sans lire les fichiers audio."""
    _ensure_dir()
    try:
        files = [p for p in CACHE_DIR.glob("*.mp3") if p.is_file()]
        total_bytes = sum(p.stat().st_size for p in files)
    except Exception:
        files = []
        total_bytes = 0
    return {
        "dir": str(CACHE_DIR),
        "entries": len(files),
        "max_entries": CACHE_MAX_ENTRIES,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
    }


async def prewarm(synthesize_to_file, voice: str, backend_name: str) -> int:
    """Pré-synthétise les phrases cibles qui manquent encore au cache.

    Renvoie le nombre de phrases effectivement générées. Appelé au démarrage.
    """
    _ensure_dir()
    added = 0
    for phrase in PREWARM_PHRASES:
        try:
            texte_naturalise = naturaliser(phrase)
            key = _cache_key(texte_naturalise, voice, backend_name)
            dst = _cache_path(key)
            if dst.exists() and dst.stat().st_size > 0:
                continue
            tmp = str(CACHE_DIR / f".tmp_{int(time.time()*1000)}_{key}.mp3")
            await synthesize_to_file(texte_naturalise, tmp)
            if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                shutil.move(tmp, dst)
                added += 1
        except Exception as e:
            print(f"[CACHE-TTS] prewarm a raté '{phrase[:40]}...' : {e}")
            continue
    if added:
        print(f"[CACHE-TTS] {added} phrases ajoutées au cache.")
    return added
