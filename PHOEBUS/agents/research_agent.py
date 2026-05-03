# PHOEBUS/agents/research_agent.py
import asyncio
from PHOEBUS.ai import demander_ia

class ResearchAgent:
    def __init__(self):
        pass

    async def search_web(self, query: str):
        """Recherche sur le web via les outils existants"""
        try:
            from PHOEBUS.skills.network_skills import recherche_web_serpapi
            results = await recherche_web_serpapi(query)
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def deep_research(self, topic: str):
        """Analyse approfondie d'un sujet en croisant plusieurs sources"""
        search_results = await self.search_web(topic)
        if not search_results["success"]:
            return search_results
        
        prompt = f"Analyse ces résultats de recherche et fais une synthèse détaillée pour Floriace :\n{search_results['results']}"
        synthesis = await demander_ia(prompt)
        return {"success": True, "synthesis": synthesis}
