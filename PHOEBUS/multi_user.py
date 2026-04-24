# PHOEBUS/multi_user.py
"""
Reconnaissance multi-utilisateurs pour PHOEBUS.

Permet à PHOEBUS d'identifier qui parle et d'adapter ses réponses.
Les profils sont enregistrés lors d'une phase d'apprentissage vocale.

Approche :
  1. Extraction d'embedding vocal via resemblyzer (si dispo) ou via
     MFCC scipy (fallback simple, moins précis mais zéro dépendance lourde).
  2. Comparaison cosinus avec les profils enregistrés.
  3. Si la confiance est > seuil, le nom du speaker est renvoyé.
  4. Sinon : "inconnu" → PHOEBUS utilise le comportement par défaut.

Variables d'environnement :
  PHOEBUS_MULTI_USER=1           → active la reconnaissance (désactivé par défaut)
  PHOEBUS_SPEAKER_THRESHOLD=0.75 → seuil de confiance (0.0–1.0)

API publique :
  enregistrer_voix(nom, audio_data) → enregistre 30s de voix d'un utilisateur
  identifier_speaker(audio_data)    → renvoie (nom, confiance) ou ("inconnu", 0.0)
  lister_utilisateurs()             → liste les profils connus
  supprimer_utilisateur(nom)        → supprime un profil
  get_profil_actif()                → nom du dernier speaker identifié
"""
import os
import json
import time
import threading
import hashlib
from pathlib import Path
from typing import Optional, Tuple

from PHOEBUS.config import BASE_DIR

# ── Configuration ─────────────────────────────────────────────────────────────

MULTI_USER_ENABLED   = os.getenv("PHOEBUS_MULTI_USER", "0").strip() == "1"
SPEAKER_THRESHOLD    = float(os.getenv("PHOEBUS_SPEAKER_THRESHOLD", "0.75"))
PROFILES_DIR         = BASE_DIR / "PHOEBUS_speaker_profiles"
PROFILES_INDEX_FILE  = PROFILES_DIR / "index.json"

# ── État ──────────────────────────────────────────────────────────────────────

_profil_actif: str = "Floriace"   # Toujours Floriace par défaut
_lock = threading.Lock()
_embeddings_cache: dict = {}       # {nom: np.array}


# ── Chargement des profils ────────────────────────────────────────────────────

def _load_index() -> dict:
    if PROFILES_INDEX_FILE.exists():
        try:
            with open(PROFILES_INDEX_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_index(index: dict):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def lister_utilisateurs() -> list:
    """Renvoie la liste des profils vocaux enregistrés."""
    return list(_load_index().keys())


def supprimer_utilisateur(nom: str) -> bool:
    index = _load_index()
    if nom not in index:
        return False
    # Supprimer le fichier d'embedding
    emb_path = Path(index[nom].get("embedding_path", ""))
    if emb_path.exists():
        try:
            emb_path.unlink()
        except Exception:
            pass
    del index[nom]
    _save_index(index)
    with _lock:
        _embeddings_cache.pop(nom, None)
    return True


def get_profil_actif() -> str:
    """Renvoie le nom du dernier speaker identifié."""
    return _profil_actif


# ── Backend resemblyzer (haute qualité) ──────────────────────────────────────

def _try_resemblyzer_embed(audio_data) -> Optional[object]:
    """Extrait un embedding vocal via resemblyzer. Renvoie None si indispo."""
    try:
        import numpy as np
        from resemblyzer import VoiceEncoder, preprocess_wav
        import tempfile, wave
        encoder = VoiceEncoder()
        wav_bytes = audio_data.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            path = f.name
        wav = preprocess_wav(path)
        os.remove(path)
        return encoder.embed_utterance(wav)
    except Exception:
        return None


# ── Backend MFCC scipy (fallback léger) ──────────────────────────────────────

def _mfcc_embed(audio_data) -> Optional[object]:
    """Embedding basique via MFCC scipy — moins précis mais sans dépendance."""
    try:
        import numpy as np
        from scipy.io import wavfile
        import tempfile
        wav_bytes = audio_data.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            path = f.name
        rate, data = wavfile.read(path)
        os.remove(path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        # MFCC maison simplifié : spectre de puissance par bandes
        from numpy.fft import rfft
        n = min(len(data), rate * 5)  # max 5s
        data = data[:n]
        window = np.hamming(n)
        spectrum = np.abs(rfft(data * window))
        # 40 bandes mel
        bands = np.array_split(spectrum, 40)
        features = np.array([b.mean() for b in bands])
        norm = np.linalg.norm(features)
        if norm > 0:
            features /= norm
        return features
    except Exception as e:
        print(f"[MULTIUSER] MFCC embed error : {e}")
        return None


def _get_embedding(audio_data):
    """Tente resemblyzer, fallback MFCC."""
    emb = _try_resemblyzer_embed(audio_data)
    if emb is not None:
        return emb, "resemblyzer"
    emb = _mfcc_embed(audio_data)
    return emb, "mfcc"


def _cosine_sim(a, b) -> float:
    try:
        import numpy as np
        a, b = np.array(a), np.array(b)
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
    except Exception:
        return 0.0


# ── Enregistrement ────────────────────────────────────────────────────────────

def enregistrer_voix(nom: str, audio_data) -> str:
    """Enregistre l'empreinte vocale d'un utilisateur.

    `audio_data` : objet AudioData de speech_recognition.
    Renvoie un message de confirmation ou d'erreur.
    """
    nom = nom.strip().title()
    emb, backend = _get_embedding(audio_data)
    if emb is None:
        return f"Impossible d'extraire l'empreinte vocale ({backend})."

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    import numpy as np
    emb_path = PROFILES_DIR / f"{hashlib.md5(nom.encode()).hexdigest()}.npy"
    np.save(str(emb_path), emb)

    index = _load_index()
    index[nom] = {
        "embedding_path": str(emb_path),
        "backend":        backend,
        "ts":             time.strftime("%Y-%m-%d %H:%M"),
    }
    _save_index(index)

    with _lock:
        _embeddings_cache[nom] = emb

    print(f"[MULTIUSER] Profil '{nom}' enregistré (backend={backend}).")
    return f"Profil vocal de {nom} enregistré avec succès."


# ── Identification ────────────────────────────────────────────────────────────

def _load_all_embeddings():
    """Charge tous les embeddings en cache si pas encore fait."""
    import numpy as np
    index = _load_index()
    with _lock:
        for nom, info in index.items():
            if nom not in _embeddings_cache:
                try:
                    emb = np.load(info["embedding_path"])
                    _embeddings_cache[nom] = emb
                except Exception:
                    pass


def identifier_speaker(audio_data) -> Tuple[str, float]:
    """Identifie le locuteur à partir d'un enregistrement audio.

    Renvoie (nom, confiance) ou ("inconnu", 0.0) si sous le seuil.
    Met à jour `_profil_actif`.
    """
    global _profil_actif

    if not MULTI_USER_ENABLED:
        return ("Floriace", 1.0)

    index = _load_index()
    if not index:
        return ("Floriace", 1.0)  # Pas de profils = Floriace par défaut

    emb, backend = _get_embedding(audio_data)
    if emb is None:
        return (_profil_actif, 0.5)

    _load_all_embeddings()

    best_nom = "inconnu"
    best_score = 0.0

    with _lock:
        for nom, stored_emb in _embeddings_cache.items():
            score = _cosine_sim(emb, stored_emb)
            if score > best_score:
                best_score = score
                best_nom = nom

    if best_score >= SPEAKER_THRESHOLD:
        _profil_actif = best_nom
        return (best_nom, best_score)
    else:
        # Sous le seuil : si un seul profil existe (Floriace seul chez lui), on lui attribue
        if len(index) == 1:
            nom = list(index.keys())[0]
            _profil_actif = nom
            return (nom, best_score)
        return ("inconnu", best_score)


# ── Phrases d'accueil personnalisées ─────────────────────────────────────────

ACCUEILS_PERSONNALISES = {
    "Floriace": [
        "Bonjour Monsieur. Que puis-je faire pour vous ?",
        "Bonsoir Floriace. Je vous écoute.",
    ],
    "Julie": [
        "Bonjour Julie ! Comment puis-je vous aider ?",
        "Bonsoir Julie !",
    ],
    "Esteban": [
        "Hey Esteban ! Qu'est-ce que je peux faire pour toi ?",
    ],
}

DEFAULT_ACCUEIL = "Bonjour ! Je vous écoute."


def get_accueil(nom: str) -> str:
    """Renvoie une phrase d'accueil personnalisée selon le speaker."""
    import random
    phrases = ACCUEILS_PERSONNALISES.get(nom, [DEFAULT_ACCUEIL])
    return random.choice(phrases)
