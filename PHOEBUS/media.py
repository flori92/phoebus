"""Aides media/VOD pour recommandations et ouverture de plateformes legales."""

from __future__ import annotations

from urllib.parse import quote_plus

import requests

from PHOEBUS.config import SERPAPI_API_KEY
from PHOEBUS.utils import open_uri


GENRE_LABELS = {
    "comedie": "comique",
    "action": "d'action",
    "science-fiction": "de science-fiction",
    "horreur": "d'horreur",
    "thriller": "thriller",
    "animation": "d'animation",
    "drame": "dramatique",
    "famille": "familial",
}

FALLBACK_TITLES = {
    "comedie": ["Le Dîner de cons", "Intouchables", "The Nice Guys"],
    "action": ["Mad Max: Fury Road", "John Wick", "Mission: Impossible - Fallout"],
    "science-fiction": ["Dune", "Blade Runner 2049", "Premier Contact"],
    "horreur": ["Sans un bruit", "Get Out", "Conjuring"],
    "thriller": ["Gone Girl", "Prisoners", "Zodiac"],
    "animation": ["Spider-Man: New Generation", "Le Voyage de Chihiro", "Klaus"],
    "famille": ["Paddington 2", "Retour vers le futur", "Jumanji"],
}

PLATFORM_URLS = {
    "justwatch": "https://www.justwatch.com/fr/recherche?q={query}",
    "netflix": "https://www.netflix.com/search?q={query}",
    "prime": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}",
    "prime video": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}",
    "disney": "https://www.disneyplus.com/search",
    "disney+": "https://www.disneyplus.com/search",
    "canal": "https://www.canalplus.com/recherche/{query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
}


def _serpapi_configured() -> bool:
    value = (SERPAPI_API_KEY or "").strip()
    if not value:
        return False
    return "VOTRE" not in value.upper() and "CHANGE" not in value.upper()


def _platform_url(platform: str, query: str) -> str:
    key = (platform or "justwatch").strip().lower()
    template = PLATFORM_URLS.get(key, PLATFORM_URLS["justwatch"])
    return template.format(query=quote_plus(query))


def _search_suggestions(query: str) -> list[str]:
    if not _serpapi_configured():
        return []
    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_API_KEY,
                "hl": "fr",
                "gl": "fr",
                "num": 5,
            },
            timeout=8,
        )
        data = response.json()
    except Exception as e:
        print(f"[MEDIA] Recherche SerpAPI indisponible : {e}")
        return []

    titles = []
    for item in data.get("organic_results", [])[:5]:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        title = title.split(" - ")[0].split(" | ")[0].strip()
        if title and title not in titles:
            titles.append(title)
    return titles[:3]


def recommander_media(
    kind: str = "film",
    genre: str = "comedie",
    platform: str = "justwatch",
    query: str | None = None,
    open_platform: bool = True,
) -> str:
    kind = (kind or "film").strip().lower()
    genre = (genre or "comedie").strip().lower()
    platform = (platform or "justwatch").strip().lower()

    genre_label = GENRE_LABELS.get(genre, genre)
    search_terms = query or f"{kind} {genre_label}"
    if platform == "justwatch":
        search_terms = f"{search_terms} streaming"

    if open_platform:
        open_uri(_platform_url(platform, search_terms))

    serp_query = f"meilleurs {kind}s {genre_label} streaming France"
    suggestions = _search_suggestions(serp_query) or FALLBACK_TITLES.get(genre, [])
    suggestion_text = ", ".join(suggestions[:3]) if suggestions else "je cherche les options disponibles"

    platform_name = "JustWatch" if platform == "justwatch" else platform.title()
    return (
        f"J'ai ouvert {platform_name} pour chercher un {kind} {genre_label}. "
        f"Propositions rapides : {suggestion_text}."
    )
