# PHOEBUS/agents/notetaking_agent.py
from PHOEBUS.connectors.obsidian_connector import ObsidianConnector
from PHOEBUS.connectors.siyuan_connector import SiYuanConnector

class NoteTakingAgent:
    def __init__(self):
        self.obsidian = ObsidianConnector()
        self.siyuan = SiYuanConnector()

    async def add_note(self, content: str, title: str, target: str = "auto"):
        """Ajoute une note dans Obsidian, SiYuan ou les deux."""
        results = {}
        if target in ["obsidian", "auto"]:
            path = f"Notes/{title}.md"
            results["obsidian"] = await self.obsidian.write(path, content)
        
        if target in ["siyuan", "auto"]:
            path = f"/Notes/{title}"
            results["siyuan"] = await self.siyuan.write(path, content)
        
        return results

    async def search_notes(self, query: str):
        """Recherche dans tous les systèmes de notes."""
        obs_res = await self.obsidian.search(query)
        sy_res = await self.siyuan.search(query)
        return {
            "obsidian": obs_res,
            "siyuan": sy_res
        }

    async def log_daily(self, content: str):
        """Note quelque chose dans les daily notes."""
        await self.obsidian.daily_append(content)
        await self.siyuan.daily_append(content)
        return True
