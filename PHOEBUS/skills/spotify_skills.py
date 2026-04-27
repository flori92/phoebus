from PHOEBUS.skills.registry import skill
from PHOEBUS import spotify as _spotify
import asyncio

@skill(
    "spotify_play",
    risk="low",
    help_text="Joue de la musique sur Spotify",
    describe=lambda d: f"Jouer {d.get('query', 'de la musique')} sur Spotify"
)
async def spotify_play(data: dict):
    q = data.get("query")
    return await asyncio.to_thread(_spotify.jouer, q)

@skill(
    "spotify_pause",
    risk="low",
    help_text="Met la musique Spotify en pause",
    describe=lambda _: "Mettre Spotify en pause"
)
async def spotify_pause(data: dict):
    return await asyncio.to_thread(_spotify.pause)

@skill(
    "spotify_resume",
    risk="low",
    help_text="Reprend la lecture Spotify",
    describe=lambda _: "Reprendre la lecture Spotify"
)
async def spotify_resume(data: dict):
    return await asyncio.to_thread(_spotify.reprendre)

@skill(
    "spotify_next",
    risk="low",
    help_text="Passe au morceau suivant",
    describe=lambda _: "Passer au morceau suivant"
)
async def spotify_next(data: dict):
    return await asyncio.to_thread(_spotify.suivant)

@skill(
    "spotify_prev",
    risk="low",
    help_text="Revient au morceau précédent",
    describe=lambda _: "Revenir au morceau précédent"
)
async def spotify_prev(data: dict):
    return await asyncio.to_thread(_spotify.precedent)

@skill(
    "spotify_volume",
    risk="low",
    help_text="Règle le volume Spotify",
    describe=lambda d: f"Régler le volume Spotify à {d.get('volume', d.get('value'))}%"
)
async def spotify_volume(data: dict):
    v = data.get("volume") or data.get("value")
    if v is not None:
        return await asyncio.to_thread(_spotify.volume, int(v))
    return "Volume non spécifié."

@skill(
    "spotify_info",
    risk="low",
    help_text="Affiche les infos du morceau en cours",
    describe=lambda _: "Donner les informations du morceau en cours"
)
async def spotify_info(data: dict):
    return await asyncio.to_thread(_spotify.info_lecture_en_cours)

@skill(
    "spotify_like",
    risk="low",
    help_text="Aime le morceau actuel",
    describe=lambda _: "Liker le morceau actuel"
)
async def spotify_like(data: dict):
    return await asyncio.to_thread(_spotify.liker_morceau_actuel)

@skill(
    "spotify_queue",
    risk="low",
    help_text="Ajoute un morceau à la file",
    describe=lambda d: f"Ajouter {d.get('query')} à la file d'attente"
)
async def spotify_queue(data: dict):
    q = data.get("query")
    return await asyncio.to_thread(_spotify.mettre_dans_file, q)

@skill(
    "spotify_playlists",
    risk="low",
    help_text="Liste vos playlists",
    describe=lambda _: "Lister les playlists Spotify"
)
async def spotify_playlists(data: dict):
    return await asyncio.to_thread(_spotify.lister_playlists)
