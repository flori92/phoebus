# PHOEBUS/connectors/obsidian_connector.py
import PHOEBUS.obsidian as obs

class ObsidianConnector:
    async def available(self):
        return await obs.api_available()
    
    async def read(self, path: str):
        return await obs.read_note(path)
    
    async def write(self, path: str, content: str):
        return await obs.write_note(path, content)
    
    async def append(self, path: str, content: str):
        return await obs.append_note(path, content)
    
    async def search(self, query: str):
        return await obs.search_text(query)
    
    async def daily_append(self, content: str):
        return await obs.append_daily(content)
