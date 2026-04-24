# PHOEBUS/spotify.py
"""
Intégration Spotify native pour PHOEBUS.

Prérequis :
  pip install spotipy
  Variables d'environnement :
    SPOTIFY_CLIENT_ID
    SPOTIFY_CLIENT_SECRET
    SPOTIFY_REDIRECT_URI   (ex: http://localhost:8888/callback)
    SPOTIFY_DEVICE_NAME    (nom du device Spotify cible, optionnel)

Le module expose une API simple et haut niveau :
  - jouer(query)          → cherche et joue un morceau/artiste/playlist
  - pause()               → met en pause
  - reprendre()           → reprend la lecture
  - suivant()             → chanson suivante
  - precedent()           → chanson précédente
  - volume(n)             → volume 0-100
  - info_lecture_en_cours() → dict avec titre, artiste, album, pochette
  - mettre_dans_file(query) → ajoute à la file sans couper la lecture actuelle
  - liker_morceau_actuel() → like la chanson en cours

Compatible avec les commandes JSON de l'IA :
  {"action": "spotify_play",    "query": "Daft Punk"}
  {"action": "spotify_pause"}
  {"action": "spotify_resume"}
  {"action": "spotify_next"}
  {"action": "spotify_prev"}
  {"action": "spotify_volume",  "value": 60}
  {"action": "spotify_info"}
  {"action": "spotify_like"}
  {"action": "spotify_queue",   "query": "One More Time"}
"""
import os
import time
import threading
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback").strip()
SPOTIFY_DEVICE_NAME   = os.getenv("SPOTIFY_DEVICE_NAME", "").strip()

# Scopes nécessaires
_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "user-library-modify "
    "playlist-read-private "
    "playlist-modify-public"
)

# ── Client Spotipy ────────────────────────────────────────────────────────────

_sp = None
_sp_lock = threading.Lock()
_device_id_cache: Optional[str] = None


def _get_client():
    """Renvoie le client Spotipy initialisé (lazy, thread-safe)."""
    global _sp
    with _sp_lock:
        if _sp is not None:
            return _sp
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            return None
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            auth_manager = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=_SCOPES,
                open_browser=False,
                cache_path=".spotify_cache",
            )
            _sp = spotipy.Spotify(auth_manager=auth_manager)
            _sp.current_user()  # Vérifie que le token est valide
            print("[SPOTIFY] Client Spotipy initialisé avec succès.")
            return _sp
        except Exception as e:
            print(f"[SPOTIFY] Impossible d'initialiser Spotipy : {e}")
            return None


def _get_device_id() -> Optional[str]:
    """Cherche l'ID du device Spotify actif (ou celui configuré)."""
    global _device_id_cache
    sp = _get_client()
    if not sp:
        return None
    try:
        devices = sp.devices().get("devices", [])
        if not devices:
            return None
        if SPOTIFY_DEVICE_NAME:
            for d in devices:
                if SPOTIFY_DEVICE_NAME.lower() in (d.get("name") or "").lower():
                    _device_id_cache = d["id"]
                    return _device_id_cache
        # Prend le device actif sinon le premier
        for d in devices:
            if d.get("is_active"):
                _device_id_cache = d["id"]
                return _device_id_cache
        _device_id_cache = devices[0]["id"]
        return _device_id_cache
    except Exception as e:
        print(f"[SPOTIFY] Erreur get_device : {e}")
        return None


def is_available() -> bool:
    """Renvoie True si Spotify est configuré et accessible."""
    return _get_client() is not None


# ── Helpers de recherche ──────────────────────────────────────────────────────

def _search_uri(query: str) -> Optional[str]:
    """Recherche le meilleur résultat (track > playlist > album > artist)."""
    sp = _get_client()
    if not sp or not query:
        return None
    try:
        # Priorité 1 : morceau exact
        results = sp.search(q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
        # Priorité 2 : playlist
        results = sp.search(q=query, type="playlist", limit=1)
        items = results.get("playlists", {}).get("items", [])
        if items:
            return items[0]["uri"]
        # Priorité 3 : album
        results = sp.search(q=query, type="album", limit=1)
        items = results.get("albums", {}).get("items", [])
        if items:
            return items[0]["uri"]
        # Priorité 4 : artiste (on joue le top)
        results = sp.search(q=query, type="artist", limit=1)
        items = results.get("artists", {}).get("items", [])
        if items:
            return items[0]["uri"]
    except Exception as e:
        print(f"[SPOTIFY] Erreur search : {e}")
    return None


# ── API publique ──────────────────────────────────────────────────────────────

def jouer(query: str) -> str:
    """Lance la lecture d'un morceau, artiste, album ou playlist."""
    sp = _get_client()
    if not sp:
        return "Spotify n'est pas configuré. Ajoutez SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET dans le fichier .env."
    uri = _search_uri(query)
    if not uri:
        return f"Impossible de trouver '{query}' sur Spotify."
    try:
        device_id = _get_device_id()
        if "track" in uri:
            sp.start_playback(device_id=device_id, uris=[uri])
        else:
            sp.start_playback(device_id=device_id, context_uri=uri)
        # Attendre un peu puis récupérer le titre
        time.sleep(0.8)
        info = info_lecture_en_cours()
        if info:
            return f"Je lance '{info['titre']}' de {info['artiste']} sur Spotify."
        return f"Lecture lancée sur Spotify pour : {query}."
    except Exception as e:
        return f"Erreur Spotify lors de la lecture : {e}"


def pause() -> str:
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        sp.pause_playback(device_id=_get_device_id())
        return "Spotify mis en pause."
    except Exception as e:
        return f"Erreur pause Spotify : {e}"


def reprendre() -> str:
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        sp.start_playback(device_id=_get_device_id())
        return "Lecture Spotify reprise."
    except Exception as e:
        return f"Erreur reprise Spotify : {e}"


def suivant() -> str:
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        sp.next_track(device_id=_get_device_id())
        time.sleep(0.8)
        info = info_lecture_en_cours()
        if info:
            return f"Chanson suivante : '{info['titre']}' de {info['artiste']}."
        return "Chanson suivante."
    except Exception as e:
        return f"Erreur Spotify : {e}"


def precedent() -> str:
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        sp.previous_track(device_id=_get_device_id())
        return "Retour à la chanson précédente."
    except Exception as e:
        return f"Erreur Spotify : {e}"


def volume(niveau: int) -> str:
    """Règle le volume Spotify (0–100)."""
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    niveau = max(0, min(100, int(niveau)))
    try:
        sp.volume(niveau, device_id=_get_device_id())
        return f"Volume Spotify réglé sur {niveau}%."
    except Exception as e:
        return f"Erreur volume Spotify : {e}"


def info_lecture_en_cours() -> Optional[dict]:
    """Renvoie un dict {titre, artiste, album, pochette_url, progression_s, duree_s}."""
    sp = _get_client()
    if not sp:
        return None
    try:
        current = sp.currently_playing()
        if not current or not current.get("item"):
            return None
        item = current["item"]
        artistes = ", ".join(a["name"] for a in item.get("artists", []))
        images = item.get("album", {}).get("images", [])
        pochette = images[0]["url"] if images else None
        return {
            "titre":         item.get("name", ""),
            "artiste":       artistes,
            "album":         item.get("album", {}).get("name", ""),
            "pochette_url":  pochette,
            "progression_s": (current.get("progress_ms") or 0) // 1000,
            "duree_s":       (item.get("duration_ms") or 0) // 1000,
            "en_lecture":    current.get("is_playing", False),
        }
    except Exception as e:
        print(f"[SPOTIFY] Erreur info : {e}")
        return None


def mettre_dans_file(query: str) -> str:
    """Ajoute un morceau à la file d'attente sans couper la lecture."""
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    uri = _search_uri(query)
    if not uri or "track" not in uri:
        # Si ce n'est pas un track, prendre le premier track de la playlist
        try:
            results = sp.search(q=query, type="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if items:
                uri = items[0]["uri"]
            else:
                return f"Impossible de trouver '{query}' à ajouter à la file."
        except Exception:
            return f"Erreur lors de la recherche de '{query}'."
    try:
        sp.add_to_queue(uri, device_id=_get_device_id())
        return f"'{query}' ajouté à la file Spotify."
    except Exception as e:
        return f"Erreur file Spotify : {e}"


def liker_morceau_actuel() -> str:
    """Like le morceau en cours de lecture."""
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        info = info_lecture_en_cours()
        if not info:
            return "Je ne détecte aucune lecture en cours sur Spotify."
        current = sp.currently_playing()
        track_id = current["item"]["id"]
        sp.current_user_saved_tracks_add([track_id])
        return f"J'ai liké '{info['titre']}' de {info['artiste']}."
    except Exception as e:
        return f"Erreur like Spotify : {e}"


def lister_playlists(limit: int = 10) -> str:
    """Liste les playlists de l'utilisateur."""
    sp = _get_client()
    if not sp:
        return "Spotify non disponible."
    try:
        playlists = sp.current_user_playlists(limit=limit)
        items = playlists.get("items", [])
        if not items:
            return "Vous n'avez aucune playlist sur Spotify."
        noms = [f"{i+1}. {p['name']} ({p.get('tracks', {}).get('total', '?')} titres)"
                for i, p in enumerate(items)]
        return "Vos playlists Spotify : " + ", ".join(noms) + "."
    except Exception as e:
        return f"Erreur playlists Spotify : {e}"
