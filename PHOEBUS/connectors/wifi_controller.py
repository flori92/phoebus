# phoebus/connectors/wifi_controller.py
import subprocess
import os

class NetworkController:
    def __init__(self, router_ip: str = "192.168.1.1"):
        self.router_ip = router_ip
    
    def scan_network(self) -> list:
        """Scanne les appareils sur le réseau (mDNS + ARP)"""
        devices = []
        try:
            # On utilise les outils système pour plus de fiabilité
            from PHOEBUS.network import scan_devices
            import asyncio
            # Attention: ici on est en synchrone dans la classe
            return [] # Placeholder - sera implémenté via orchestrator
        except:
            return []

    def get_wifi_info(self) -> dict:
        """Info sur la connexion WiFi actuelle (macOS)"""
        if os.path.exists("/usr/sbin/networksetup"):
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True, text=True
            )
            return {"network": result.stdout.strip()}
        return {"network": "Inconnu"}
    
    def ping_device(self, ip: str) -> bool:
        """Vérifie si un appareil est en ligne"""
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True
        )
        return result.returncode == 0
