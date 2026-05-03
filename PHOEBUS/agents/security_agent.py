# PHOEBUS/agents/security_agent.py
import os
import json
from datetime import datetime
from PHOEBUS.rag_memory import stocker_souvenir

class SecurityAgent:
    def __init__(self):
        self.location_history_file = "data/phone_location_history.jsonl"
        os.makedirs("data", exist_ok=True)

    def update_location(self, lat, lon, metadata=None):
        """Met à jour la position connue du téléphone."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "lat": lat,
            "lon": lon,
            "metadata": metadata or {}
        }
        with open(self.location_history_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        # On peut aussi le stocker dans la mémoire long terme si c'est un changement notable
        stocker_souvenir(f"Position téléphone mise à jour : {lat}, {lon}", source="satellite", importance=1)
        return True

    async def locate_phone(self, **kwargs):
        """Retourne la dernière position connue."""
        if not os.path.exists(self.location_history_file):
            return {"success": False, "error": "Aucun historique de position trouvé."}
        
        last_entry = None
        with open(self.location_history_file, "r") as f:
            for line in f:
                last_entry = json.loads(line)
        
        if last_entry:
            return {
                "success": True, 
                "location": f"Latitude: {last_entry['lat']}, Longitude: {last_entry['lon']}",
                "time": last_entry['timestamp'],
                "map_url": f"https://www.google.com/maps?q={last_entry['lat']},{last_entry['lon']}"
            }
        return {"success": False, "error": "Position introuvable."}

    async def trigger_alarm(self, **kwargs):
        """Déclenche une alarme sur le téléphone (via l'app satellite)."""
        # On ajoute une commande dans la file d'attente pour l'iPhone
        from PHOEBUS.state import IOS_PENDING_COMMANDS
        IOS_PENDING_COMMANDS.append({"action": "play_alarm", "volume": 1.0})
        return {"success": True, "message": "Signal d'alarme envoyé au téléphone."}

    async def emergency_lock(self, **kwargs):
        """Action d'urgence en cas de vol."""
        await self.trigger_alarm()
        stocker_souvenir("ALERTE VOL : Tentative de verrouillage à distance.", source="security", importance=5)
        # Ici on pourrait intégrer pyicloud pour un vrai verrouillage
        return {"success": True, "message": "Mode urgence activé. Alarme déclenchée et incident enregistré."}
