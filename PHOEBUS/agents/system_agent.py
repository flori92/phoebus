# phoebus/agents/system_agent.py
import subprocess
import platform
import psutil
import os

class SystemAgent:
    def __init__(self):
        self.os_type = platform.system()  # 'Darwin' pour Mac, 'Windows' pour PC
    
    # ========== COMMANDES UNIVERSELLES ==========
    
    def execute_command(self, command: str, shell: str = None) -> dict:
        """Exécute une commande système avec logging"""
        if shell is None:
            shell = "zsh" if self.os_type == "Darwin" else "powershell"
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                executable=f"/bin/{shell}" if self.os_type == "Darwin" else None
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout dépassé"}
    
    # ========== INFOS SYSTÈME ==========
    
    def get_system_info(self) -> dict:
        return {
            "os": platform.platform(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram": {
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "used_percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "used_percent": round(psutil.disk_usage('/').percent, 2)
            },
            "battery": self._get_battery(),
            "processes_count": len(psutil.pids())
        }
    
    # ========== CONTRÔLE APPLICATIONS ==========
    
    def open_app(self, app_name: str) -> dict:
        if self.os_type == "Darwin":
            return self.execute_command(f"open -a '{app_name}'")
        else:
            return self.execute_command(f"Start-Process '{app_name}'")
    
    def close_app(self, app_name: str) -> dict:
        if self.os_type == "Darwin":
            return self.execute_command(
                f"osascript -e 'quit app \"{app_name}\"'"
            )
        else:
            return self.execute_command(
                f"Stop-Process -Name '{app_name}' -Force"
            )
    
    def list_running_apps(self) -> list:
        if self.os_type == "Darwin":
            result = self.execute_command(
                "osascript -e 'tell application \"System Events\" to get name of every process whose background only is false'"
            )
            return result["stdout"].split(", ") if result["success"] else []
        else:
            result = self.execute_command(
                "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty ProcessName"
            )
            return result["stdout"].split("\n") if result["success"] else []
    
    # ========== CONTRÔLE MAC SPÉCIFIQUE ==========
    
    def mac_set_volume(self, level: int) -> dict:
        """Volume de 0 à 100"""
        return self.execute_command(
            f"osascript -e 'set volume output volume {level}'"
        )
    
    def mac_set_brightness(self, level: float) -> dict:
        """Luminosité de 0 à 1"""
        return self.execute_command(f"brightness {level}")
    
    def mac_screenshot(self, path: str = "/tmp/screenshot.png") -> dict:
        return self.execute_command(f"screencapture -x {path}")
    
    def mac_say(self, text: str) -> dict:
        """Synthèse vocale native macOS"""
        return self.execute_command(f'say "{text}"')
    
    def mac_notification(self, title: str, message: str) -> dict:
        return self.execute_command(
            f'''osascript -e 'display notification "{message}" with title "{title}"' '''
        )
    
    def mac_dark_mode_toggle(self) -> dict:
        return self.execute_command(
            '''osascript -e 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode' '''
        )
    
    # ========== CONTRÔLE WINDOWS SPÉCIFIQUE ==========
    
    def win_lock_screen(self) -> dict:
        return self.execute_command("rundll32.exe user32.dll,LockWorkStation")
    
    def win_shutdown(self, delay: int = 60) -> dict:
        return self.execute_command(f"shutdown /s /t {delay}")
    
    # ========== GESTION FICHIERS AVANCÉE ==========
    
    def search_files(self, query: str, path: str = "~") -> dict:
        path = os.path.expanduser(path)
        if self.os_type == "Darwin":
            return self.execute_command(f"mdfind -onlyin {path} '{query}'")
        else:
            return self.execute_command(
                f"Get-ChildItem -Path {path} -Recurse -Filter '*{query}*' -ErrorAction SilentlyContinue | Select-Object FullName"
            )
    
    def _get_battery(self):
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "plugged": battery.power_plugged
            }
        return None
