# PHOEBUS/connectors/siyuan_connector.py
import PHOEBUS.siyuan as sy

class SiYuanConnector:
    async def available(self):
        return await sy.api_available()
    
    async def read(self, path: str):
        return await sy.read_doc_by_path(path)
    
    async def write(self, path: str, content: str):
        return await sy.create_doc(path, content)
    
    async def append(self, path: str, content: str):
        # On essaie de trouver l'ID du doc d'abord
        doc_id = await sy._get_doc_id_by_path(path, await sy._resolve_default_notebook())
        if doc_id:
            return await sy.append_block(doc_id, content)
        return False
    
    async def search(self, query: str):
        return await sy.search_text(query)
    
    async def daily_append(self, content: str):
        return await sy.append_daily(content)
