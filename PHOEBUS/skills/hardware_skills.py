from PHOEBUS.skills.registry import skill
import psutil
import platform
import socket
import requests

@skill(
    "system_stats",
    risk="low",
    help_text="Donne les statistiques vitales du matériel (CPU, RAM, Batterie)",
    describe=lambda _: "Analyser l'état de santé du système"
)
async def system_stats(data: dict):
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    
    msg = f"L'état du système est optimal. Utilisation CPU à {cpu}%, mémoire vive à {ram}%."
    if battery:
        msg += f" La batterie est à {battery.percent}% et {'en charge' if battery.power_plugged else 'sur batterie'}."
    
    return msg

@skill(
    "network_info",
    risk="low",
    help_text="Donne des infos sur la connexion et la localisation IP",
    describe=lambda _: "Vérifier la configuration réseau et la localisation"
)
async def network_info(data: dict):
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    try:
        # On récupère la localisation basée sur l'IP publique (inspiré de Jarvis)
        response = requests.get('https://ipapi.co/json/', timeout=5).json()
        city = response.get('city')
        region = response.get('region')
        country = response.get('country_name')
        isp = response.get('org')
        
        return (f"Connecté via {isp}. Ma position réseau actuelle est {city}, {region} en {country}. "
                f"Mon adresse IP locale sur le réseau de Floriace est {local_ip}.")
    except:
        return f"Je suis connecté sur le réseau local avec l'adresse {local_ip}. Impossible de joindre les serveurs de localisation."
