from PHOEBUS.skills.registry import skill
from PHOEBUS import home as _home
import asyncio

@skill(
    "meteo",
    risk="low",
    help_text="Donne la météo actuelle pour une ville",
    describe=lambda d: f"Vérifier la météo à {d.get('ville', 'ma position')}"
)
async def skill_meteo(data: dict):
    ville = data.get("ville")
    return await asyncio.to_thread(_home.get_meteo_actuelle, ville, data.get("periode"))

@skill(
    "alerte_meteo",
    risk="low",
    help_text="Vérifie les alertes météo (orages, pluie) pour les jours à venir",
    describe=lambda d: f"Vérifier les alertes météo à {d.get('ville', 'ma position')}"
)
async def skill_alerte_meteo(data: dict):
    ville = data.get("ville")
    return await asyncio.to_thread(_home.get_alertes_meteo, ville)

@skill(
    "recherche_web",
    risk="low",
    help_text="Effectue une recherche en temps réel sur Internet via SerpAPI",
    describe=lambda d: f"Rechercher sur le web : {d.get('query')}"
)
async def skill_recherche_web(data: dict):
    q = data.get("query")
    if not q:
        return "Que voulez-vous que je cherche ?"
    return _home.recherche_web_serpapi(q)

@skill(
    "knowledge_query",
    risk="low",
    help_text="Répond à une question de connaissance générale via Wikipédia/Wolfram",
    describe=lambda d: f"Chercher une réponse pour : {d.get('question')}"
)
async def skill_knowledge_query(data: dict):
    from PHOEBUS.knowledge import query
    q = data.get("question")
    if not q: return "Je n'ai pas compris la question."
    return await query(q)

@skill(
    "youtube",
    risk="low",
    help_text="Cherche et lance une vidéo sur YouTube",
    describe=lambda d: f"Lancer la vidéo YouTube : {d.get('query')}"
)
async def skill_youtube(data: dict):
    q = data.get("query")
    if not q: return "Quelle vidéo dois-je chercher ?"
    
    from PHOEBUS.home import chercher_youtube
    from PHOEBUS.utils import open_uri
    url = chercher_youtube(q)
    if url:
        open_uri(url)
        return f"Je lance la vidéo sur YouTube pour : {q}."
    return "Je n'ai pas trouvé de vidéo correspondante sur YouTube."
