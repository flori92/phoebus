import asyncio
import PHOEBUS.state as state
from PHOEBUS.voice import parler

async def trigger_hook(event_name: str, data: dict = None):
    """
    Déclenche une réaction automatique de PHOEBUS suite à un événement.
    Inspiré de l'architecture Hooks de OpenJarvis.
    """
    print(f"[HOOK] Événement détecté : {event_name}")
    
    if event_name == "system_boot":
        # Action au démarrage
        pass
        
    elif event_name == "low_battery":
        await parler("Floriace, votre batterie est faible. Pensez à brancher le chargeur.", keep_conversation=False)
        
    elif event_name == "user_arrival":
        await parler(f"Bienvenue à la maison Floriace. Voulez-vous que j'allume les lumières ?", keep_conversation=True)

    elif event_name == "satellite_connected":
        client_type = (data or {}).get("client_type", "inconnu")
        print(f"[HOOK] Nouveau satellite synchronisé : {client_type}")
