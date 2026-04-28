import asyncio

from PHOEBUS.skills.registry import skill
from PHOEBUS import media as _media


@skill(
    "media_recommendations",
    risk="low",
    help_text="Recommande un film ou une serie et ouvre une plateforme VOD legale",
    describe=lambda d: f"Chercher un {d.get('kind', 'film')} {d.get('genre', '')} en streaming",
)
async def skill_media_recommendations(data: dict):
    return await asyncio.to_thread(
        _media.recommander_media,
        data.get("kind", "film"),
        data.get("genre", "comedie"),
        data.get("platform", "justwatch"),
        data.get("query"),
        bool(data.get("open", True)),
    )
