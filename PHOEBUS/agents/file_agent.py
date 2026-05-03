# PHOEBUS/agents/file_agent.py
import os
import shutil
from pathlib import Path

class FileAgent:
    def __init__(self):
        pass

    def list_dir(self, path: str = "."):
        path = os.path.expanduser(path)
        try:
            items = os.listdir(path)
            return {"success": True, "items": items}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_file(self, path: str):
        path = os.path.expanduser(path)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return {"success": True, "content": f.read()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str):
        path = os.path.expanduser(path)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_file(self, path: str):
        path = os.path.expanduser(path)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
