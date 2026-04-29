from PHOEBUS.skills.registry import skill
import psutil
import platform
import socket
import requests
import asyncio


def _format_devices(devices: list[dict], limit: int = 12) -> str:
    if not devices:
        return "Aucun appareil détecté sur le réseau local pour l'instant."
    from PHOEBUS.network import label_for_device

    labels = [label_for_device(device) for device in devices[:limit]]
    suffix = "" if len(devices) <= limit else f", et {len(devices) - limit} autre(s)"
    return "Appareils détectés : " + ", ".join(labels) + suffix + "."


@skill(
    "system_stats",
    risk="low",
    help_text="Donne les statistiques vitales du matériel (CPU, RAM, Batterie)",
    describe=lambda _: "Analyser l'état de santé du système",
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
    describe=lambda _: "Vérifier la configuration réseau et la localisation",
)
async def network_info(data: dict):
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    try:
        # On récupère la localisation basée sur l'IP publique (inspiré de Jarvis)
        response = requests.get("https://ipapi.co/json/", timeout=5).json()
        city = response.get("city")
        region = response.get("region")
        country = response.get("country_name")
        isp = response.get("org")

        return (
            f"Connecté via {isp}. Ma position réseau actuelle est {city}, {region} en {country}. "
            f"Mon adresse IP locale sur le réseau de Floriace est {local_ip}."
        )
    except:
        return f"Je suis connecté sur le réseau local avec l'adresse {local_ip}. Impossible de joindre les serveurs de localisation."


@skill(
    "network_scan",
    risk="low",
    help_text="Liste les appareils détectés sur le réseau local",
    describe=lambda _: "Scanner le réseau local",
)
async def network_scan(data: dict):
    from PHOEBUS.network import discover

    devices = await discover(refresh=bool(data.get("refresh", False)))
    return _format_devices(devices)


@skill(
    "network_ping",
    risk="low",
    help_text="Teste si une adresse IP répond au ping",
    describe=lambda d: f"Pinger {d.get('ip')}",
)
async def network_ping(data: dict):
    ip = (data.get("ip") or "").strip()
    if not ip:
        return "Adresse IP manquante."

    def _ping():
        import subprocess

        flag_timeout = "1000" if platform.system() == "Darwin" else "1"
        cmd = ["ping", "-c", "1", "-W", flag_timeout, ip]
        return (
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
            == 0
        )

    ok = await asyncio.to_thread(_ping)
    return f"{ip} répond au ping." if ok else f"{ip} ne répond pas au ping."


@skill(
    "network_ping_sweep",
    risk="low",
    help_text="Balaye le subnet local pour découvrir les hôtes actifs",
    describe=lambda _: "Balayer le subnet local",
)
async def network_ping_sweep(data: dict):
    from PHOEBUS.network import ping_sweep

    ips = await ping_sweep(data.get("subnet"))
    if not ips:
        return "Aucun hôte n'a répondu au balayage ping."
    return (
        "Hôtes actifs : "
        + ", ".join(ips[:30])
        + ("." if len(ips) <= 30 else f", et {len(ips) - 30} autre(s).")
    )


@skill(
    "network_wake",
    risk="low",
    help_text="Envoie un paquet Wake-on-LAN à une adresse MAC",
    describe=lambda d: f"Réveiller {d.get('mac')}",
)
async def network_wake(data: dict):
    from PHOEBUS.network import wake_on_lan

    mac = (data.get("mac") or "").strip()
    if not mac:
        return "Adresse MAC manquante."
    ok = await asyncio.to_thread(wake_on_lan, mac)
    return (
        "Paquet Wake-on-LAN envoyé."
        if ok
        else "Adresse MAC invalide ou envoi Wake-on-LAN impossible."
    )


@skill(
    "network_probe",
    risk="low",
    help_text="Sonde les services courants ouverts sur une IP",
    describe=lambda d: f"Sonder les services de {d.get('ip')}",
)
async def network_probe(data: dict):
    from PHOEBUS.network import probe_services

    ip = (data.get("ip") or "").strip()
    if not ip:
        return "Adresse IP manquante."
    services = await probe_services(ip)
    if not services:
        return f"Aucun service courant détecté sur {ip}."
    details = ", ".join(f"{port}/{name}" for port, name in sorted(services.items()))
    return f"Services détectés sur {ip} : {details}."
