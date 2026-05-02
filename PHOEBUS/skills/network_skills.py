# PHOEBUS/skills/network_skills.py
"""Contrôle réseau total de PHOEBUS — Discovery, WOL, SSH, ADB, Pushcut.

Phoebus peut :
- Scanner le réseau local et lister TOUS les appareils connectés
- Réveiller un PC via Wake-on-LAN (WOL)
- Exécuter des commandes à distance via SSH (Linux/Mac)
- Contrôler un Android via ADB WiFi
- Déclencher des Raccourcis iOS via Pushcut webhook
- Bloquer/débloquer des appareils (via iptables ou routeur)
"""

import asyncio
import json
import os
import re
import socket
import subprocess
import struct
import time
from pathlib import Path
from typing import Optional

from PHOEBUS.config import BASE_DIR
from PHOEBUS.skills.registry import skill

# ── Configuration ──────────────────────────────────────────────────────────

DEVICES_DB = Path(BASE_DIR) / "phoebus_network_devices.json"
PUSHCUT_URL = os.getenv("PHOEBUS_PUSHCUT_URL", "").strip()
PUSHCUT_API_KEY = os.getenv("PHOEBUS_PUSHCUT_API_KEY", "").strip()
ADB_PATH = os.getenv("PHOEBUS_ADB_PATH", "adb").strip()


# ── Base de données des appareils connus ───────────────────────────────────

def _load_devices() -> dict:
    if DEVICES_DB.exists():
        try:
            return json.loads(DEVICES_DB.read_text())
        except Exception:
            pass
    return {}


def _save_devices(devices: dict):
    DEVICES_DB.write_text(json.dumps(devices, indent=2, ensure_ascii=False, default=str))


def _register_device(ip: str, info: dict):
    devices = _load_devices()
    key = info.get("name") or ip
    devices[key] = {**devices.get(key, {}), "ip": ip, **info, "last_seen": time.strftime("%Y-%m-%d %H:%M")}
    _save_devices(devices)


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 1 — Scan réseau complet (ARP + ports)
# ══════════════════════════════════════════════════════════════════════════════

def _get_local_subnet() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except Exception:
        return "192.168.1"


def _arp_scan() -> list[dict]:
    """Scan ARP natif — fonctionne sur Mac/Linux sans dépendance."""
    devices = []
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=15)
        # Format: hostname (192.168.1.X) at aa:bb:cc:dd:ee:ff on en0
        pattern = re.compile(r"(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([\da-fA-F:]+)")
        for match in pattern.finditer(result.stdout):
            hostname, ip, mac = match.groups()
            if mac == "(incomplete)" or mac == "ff:ff:ff:ff:ff:ff":
                continue
            devices.append({
                "hostname": hostname if hostname != "?" else "",
                "ip": ip,
                "mac": mac.lower(),
            })
    except Exception as e:
        print(f"[NET] ARP scan error: {e}")
    return devices


def _identify_device(dev: dict) -> dict:
    """Tente d'identifier le type d'appareil par son MAC OUI."""
    mac = dev.get("mac", "")
    oui = mac[:8].upper() if mac else ""
    # OUI courants
    OUI_DB = {
        "A4:83:E7": "Apple", "3C:22:FB": "Apple", "F0:18:98": "Apple",
        "AC:DE:48": "Apple", "DC:A6:32": "Raspberry Pi", "B8:27:EB": "Raspberry Pi",
        "00:1A:79": "Samsung", "94:35:0A": "Samsung", "CC:46:D6": "Google",
        "30:FD:38": "Google", "54:60:09": "Google", "44:07:0B": "Google Nest",
        "F4:F5:D8": "Google", "78:8A:20": "Ubiquiti", "80:2A:A8": "Ubiquiti",
        "B4:FB:E4": "Ubiquiti", "00:50:56": "VMware", "00:0C:29": "VMware",
        "00:15:5D": "Hyper-V", "52:54:00": "QEMU/KVM",
        "00:E0:4C": "Realtek", "48:5D:60": "AzureWave",
    }
    vendor = OUI_DB.get(oui, "")
    if vendor:
        dev["vendor"] = vendor
    hostname = dev.get("hostname", "")
    # Heuristiques par hostname
    if any(k in hostname.lower() for k in ("iphone", "ipad", "macbook", "imac")):
        dev["type"] = "apple"
    elif any(k in hostname.lower() for k in ("android", "galaxy", "pixel", "oneplus")):
        dev["type"] = "android"
    elif any(k in hostname.lower() for k in ("raspberrypi", "pi-", "rpi")):
        dev["type"] = "raspberry_pi"
    elif vendor:
        dev["type"] = vendor.lower().replace(" ", "_")
    return dev


@skill(
    "network_scan",
    risk="low",
    help_text="Scanne le réseau local et liste tous les appareils connectés",
    describe=lambda d: "Scanner le réseau local",
)
async def network_scan(data: dict):
    """Scan ARP du réseau local."""
    devices = await asyncio.to_thread(_arp_scan)
    if not devices:
        return "Aucun appareil trouvé sur le réseau. Vérifie ta connexion."

    devices = [_identify_device(d) for d in devices]

    # Enregistrer dans la base
    for d in devices:
        _register_device(d["ip"], d)

    lines = [f"**{len(devices)} appareil(s) sur le réseau :**"]
    for d in sorted(devices, key=lambda x: x["ip"]):
        name = d.get("hostname") or "?"
        vendor = d.get("vendor", "")
        typ = d.get("type", "")
        extra = f" ({vendor})" if vendor else (f" [{typ}]" if typ else "")
        lines.append(f"  • **{d['ip']}** — {name}{extra} [{d['mac']}]")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 2 — Wake-on-LAN (allumer un PC à distance)
# ══════════════════════════════════════════════════════════════════════════════

def _send_wol(mac: str, broadcast: str = "255.255.255.255"):
    """Envoie un magic packet Wake-on-LAN."""
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    magic = b"\xff" * 6 + mac_bytes * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(magic, (broadcast, 9))
    sock.close()


@skill(
    "wake_on_lan",
    risk="medium",
    help_text="Réveille un PC à distance via Wake-on-LAN",
    describe=lambda d: f"Réveiller {d.get('name', d.get('mac', '?'))} via WOL",
)
async def wake_on_lan(data: dict):
    mac = data.get("mac", "").strip()
    name = data.get("name", "").strip()

    # Chercher dans la base si on a un nom
    if not mac and name:
        devices = _load_devices()
        for dname, dinfo in devices.items():
            if name.lower() in dname.lower():
                mac = dinfo.get("mac", "")
                break

    if not mac or len(mac.replace(":", "").replace("-", "")) != 12:
        return f"Adresse MAC invalide ou appareil '{name}' inconnu. Lance d'abord un scan réseau."

    try:
        await asyncio.to_thread(_send_wol, mac)
        return f"Magic packet envoyé à {mac}. L'appareil devrait s'allumer dans quelques secondes."
    except Exception as e:
        return f"Erreur WOL : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 3 — SSH Remote (contrôle Linux/Mac à distance)
# ══════════════════════════════════════════════════════════════════════════════

@skill(
    "ssh_execute",
    risk="high",
    help_text="Exécute une commande sur une machine distante via SSH",
    describe=lambda d: f"SSH sur {d.get('host', '?')} : {d.get('command', '?')[:40]}",
)
async def ssh_execute(data: dict):
    host = data.get("host", "").strip()
    user = data.get("user", "").strip() or os.getenv("USER", "pi")
    command = data.get("command", "").strip()

    if not host or not command:
        return "Il me faut un host et une commande pour exécuter via SSH."

    # Chercher dans la base
    if not re.match(r"\d+\.\d+\.\d+\.\d+", host):
        devices = _load_devices()
        for dname, dinfo in devices.items():
            if host.lower() in dname.lower():
                host = dinfo.get("ip", host)
                break

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
             f"{user}@{host}", command],
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        if result.returncode == 0:
            return f"Commande exécutée sur {host} :\n```\n{output[:1000]}\n```"
        return f"Erreur SSH (code {result.returncode}) :\n{error[:500]}"
    except subprocess.TimeoutExpired:
        return f"Timeout : la machine {host} ne répond pas en SSH."
    except Exception as e:
        return f"Erreur SSH : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 4 — ADB WiFi (contrôle Android total)
# ══════════════════════════════════════════════════════════════════════════════

@skill(
    "adb_command",
    risk="high",
    help_text="Exécute une commande ADB sur un Android connecté en WiFi",
    describe=lambda d: f"ADB sur Android : {d.get('command', '?')[:40]}",
)
async def adb_command(data: dict):
    command = data.get("command", "").strip()
    device_ip = data.get("device_ip", "").strip()

    if not command:
        return "Il me faut une commande ADB à exécuter."

    # Si on a une IP, connecter d'abord
    if device_ip:
        try:
            await asyncio.to_thread(
                subprocess.run,
                [ADB_PATH, "connect", f"{device_ip}:5555"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass

    try:
        args = [ADB_PATH, "shell"] + command.split()
        result = await asyncio.to_thread(
            subprocess.run, args,
            capture_output=True, text=True, timeout=10,
        )
        output = (result.stdout or "").strip()
        if result.returncode == 0:
            return f"ADB OK :\n```\n{output[:800]}\n```" if output else "Commande ADB exécutée."
        return f"ADB erreur : {(result.stderr or '').strip()[:500]}"
    except FileNotFoundError:
        return "ADB n'est pas installé. Installe Android SDK Platform Tools."
    except Exception as e:
        return f"Erreur ADB : {e}"


@skill(
    "adb_open_app",
    risk="medium",
    help_text="Ouvre une application sur un Android connecté via ADB",
    describe=lambda d: f"Ouvrir {d.get('app', '?')} sur Android",
)
async def adb_open_app(data: dict):
    app = data.get("app", "").strip()
    if not app:
        return "Quelle application ouvrir sur Android ?"

    # Mapping des noms courants → packages Android
    APP_PACKAGES = {
        "netflix": "com.netflix.mediaclient",
        "netflix tv": "com.netflix.ninja",
        "youtube": "com.google.android.youtube",
        "youtube tv": "com.google.android.youtube.tv",
        "spotify": "com.spotify.music",
        "spotify tv": "com.spotify.tv.android",
        "chrome": "com.android.chrome",
        "camera": "com.android.camera2",
        "settings": "com.android.settings",
        "maps": "com.google.android.apps.maps",
        "whatsapp": "com.whatsapp",
        "telegram": "org.telegram.messenger",
        "instagram": "com.instagram.android",
        "tiktok": "com.zhiliaoapp.musically",
        "twitter": "com.twitter.android",
        "discord": "com.discord",
        "prime video": "com.amazon.avod.thirdpartyclient",
        "prime tv": "com.amazon.amazonvideo.livingroom",
        "disney": "com.disney.disneyplus",
    }

    app_lower = app.lower()
    package = APP_PACKAGES.get(app_lower)
    
    # Si le package n'est pas dans la liste et contient un espace (ex: "smart tube"), on retire les espaces pour essayer de deviner
    if not package:
        package = app.replace(" ", "").lower()
        
    result_data = {"command": f"monkey -p {package} -c android.intent.category.LAUNCHER 1"}
    return await adb_command(result_data)


@skill(
    "adb_tv_control",
    risk="low",
    help_text="Contrôle une TV Android (télécommande : pause, volume, éteindre, naviguer)",
    describe=lambda d: f"Télécommande TV : {d.get('action', '?')}",
)
async def adb_tv_control(data: dict):
    action = data.get("action", "").lower().strip()
    
    # Mapping des actions en Keycodes ADB
    KEYCODES = {
        "power": 26, "eteindre": 26, "allumer": 26,
        "home": 3, "accueil": 3,
        "back": 4, "retour": 4,
        "up": 19, "haut": 19,
        "down": 20, "bas": 20,
        "left": 21, "gauche": 21,
        "right": 22, "droite": 22,
        "ok": 66, "enter": 66, "valider": 66,
        "vol+": 24, "plus fort": 24, "monter le volume": 24, "baisse": 25, # baisse interceptera "baisse le volume"
        "vol-": 25, "moins fort": 25, "baisser le volume": 25,
        "mute": 164, "muet": 164, "couper le son": 164,
        "play": 85, "pause": 85, "lecture": 85,
        "next": 87, "suivant": 87,
        "prev": 88, "precedent": 88, "précédent": 88
    }
    
    # Recherche floue
    keycode = None
    for key, code in KEYCODES.items():
        if key in action:
            keycode = code
            break
            
    if not keycode:
        # Fallback si c'est directement un numéro
        if action.isdigit():
            keycode = int(action)
        else:
            return f"Action de télécommande inconnue : '{action}'."

    return await adb_command({"command": f"input keyevent {keycode}"})

# ══════════════════════════════════════════════════════════════════════════════
# SKILL 5 — Pushcut / iOS Shortcuts Bridge
# ══════════════════════════════════════════════════════════════════════════════

@skill(
    "ios_shortcut",
    risk="medium",
    help_text="Déclenche un Raccourci Apple sur l'iPhone via Pushcut",
    describe=lambda d: f"Déclencher le raccourci iOS : {d.get('shortcut', '?')}",
)
async def ios_shortcut(data: dict):
    shortcut = data.get("shortcut", "").strip()
    input_text = data.get("input", "").strip()

    if not shortcut:
        return "Quel raccourci iOS dois-je déclencher ?"

    if not PUSHCUT_URL:
        return ("Pushcut n'est pas configuré. Ajoute PHOEBUS_PUSHCUT_URL et "
                "PHOEBUS_PUSHCUT_API_KEY dans le .env. Installe Pushcut sur ton iPhone.")

    import requests
    try:
        url = f"{PUSHCUT_URL.rstrip('/')}/notifications/{shortcut}"
        headers = {"API-Key": PUSHCUT_API_KEY} if PUSHCUT_API_KEY else {}
        payload = {}
        if input_text:
            payload["input"] = input_text

        resp = await asyncio.to_thread(
            requests.post, url, json=payload, headers=headers, timeout=10,
        )
        if resp.status_code in (200, 201):
            return f"Raccourci '{shortcut}' déclenché sur ton iPhone !"
        return f"Pushcut a répondu avec le code {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f"Erreur Pushcut : {e}"


@skill(
    "ios_open_app",
    risk="low",
    help_text="Ouvre une app sur l'iPhone via un raccourci Pushcut préconfiguré",
    describe=lambda d: f"Ouvrir {d.get('app', '?')} sur iPhone",
)
async def ios_open_app(data: dict):
    app = data.get("app", "").strip()
    if not app:
        return "Quelle application ouvrir sur l'iPhone ?"
    # Pushcut notification nommée "Ouvrir <app>" → doit exister côté iPhone
    return await ios_shortcut({"shortcut": f"Ouvrir {app}", "input": app})


@skill(
    "ios_send_message",
    risk="high",
    help_text="Envoie un message via iMessage/SMS depuis l'iPhone",
    describe=lambda d: f"Envoyer '{d.get('message', '')[:30]}' à {d.get('contact', '?')}",
)
async def ios_send_message(data: dict):
    contact = data.get("contact", "").strip()
    message = data.get("message", "").strip()
    if not contact or not message:
        return "Il me faut un contact et un message."
    return await ios_shortcut({
        "shortcut": "Envoyer Message",
        "input": json.dumps({"contact": contact, "message": message}),
    })


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 6 — Registre des appareils connus
# ══════════════════════════════════════════════════════════════════════════════

@skill(
    "device_list",
    risk="low",
    help_text="Liste tous les appareils connus du réseau (historique des scans)",
    describe=lambda d: "Lister les appareils connus",
)
async def device_list(data: dict):
    devices = _load_devices()
    if not devices:
        return "Aucun appareil connu. Lance un scan réseau d'abord."

    lines = [f"**{len(devices)} appareil(s) connus :**"]
    for name, info in sorted(devices.items()):
        ip = info.get("ip", "?")
        mac = info.get("mac", "?")
        vendor = info.get("vendor", "")
        last = info.get("last_seen", "?")
        extra = f" ({vendor})" if vendor else ""
        lines.append(f"  • **{name}** — {ip} [{mac}]{extra} (vu: {last})")
    return "\n".join(lines)


@skill(
    "device_name",
    risk="low",
    help_text="Nomme un appareil réseau pour le retrouver facilement",
    describe=lambda d: f"Nommer {d.get('ip', '?')} → {d.get('name', '?')}",
)
async def device_name(data: dict):
    ip = data.get("ip", "").strip()
    name = data.get("name", "").strip()
    if not ip or not name:
        return "Il me faut une IP et un nom pour enregistrer l'appareil."
    devices = _load_devices()
    # Trouver par IP
    for dname, dinfo in list(devices.items()):
        if dinfo.get("ip") == ip:
            info = devices.pop(dname)
            info["name"] = name
            devices[name] = info
            _save_devices(devices)
            return f"Appareil {ip} renommé en '{name}'."
    # Nouveau
    _register_device(ip, {"name": name})
    return f"Appareil '{name}' ({ip}) enregistré."


@skill(
    "device_ping",
    risk="low",
    help_text="Vérifie si un appareil réseau est en ligne (ping)",
    describe=lambda d: f"Ping {d.get('target', '?')}",
)
async def device_ping(data: dict):
    target = data.get("target", "").strip()
    if not target:
        return "Quel appareil pinger ? Donne-moi un IP, hostname ou nom."

    # Résoudre le nom
    if not re.match(r"\d+\.\d+\.\d+\.\d+", target):
        devices = _load_devices()
        for dname, dinfo in devices.items():
            if target.lower() in dname.lower():
                target = dinfo.get("ip", target)
                break

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["ping", "-c", "3", "-W", "2", target],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            # Extraire le temps moyen
            match = re.search(r"avg.*?= ([\d.]+)", result.stdout) or re.search(r"avg = ([\d.]+)", result.stdout)
            avg = match.group(1) if match else "?"
            return f"✅ {target} est en ligne (temps moyen : {avg} ms)."
        return f"❌ {target} ne répond pas au ping."
    except subprocess.TimeoutExpired:
        return f"❌ {target} ne répond pas (timeout)."
    except Exception as e:
        return f"Erreur ping : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SKILL 7 — Contrôle de bande passante / blocage
# ══════════════════════════════════════════════════════════════════════════════

@skill(
    "network_block",
    risk="high",
    help_text="Bloque un appareil du réseau local (coupe son accès internet via iptables/pf)",
    describe=lambda d: f"Bloquer {d.get('target', '?')} sur le réseau",
)
async def network_block(data: dict):
    target = data.get("target", "").strip()
    if not target:
        return "Quel appareil bloquer ?"

    # Résoudre le nom
    if not re.match(r"\d+\.\d+\.\d+\.\d+", target):
        devices = _load_devices()
        for dname, dinfo in devices.items():
            if target.lower() in dname.lower():
                target = dinfo.get("ip", target)
                break

    import platform
    system = platform.system()

    if system == "Darwin":
        # macOS : utiliser pf (packet filter) — nécessite sudo
        rule = f"block drop from {target} to any"
        return (f"Pour bloquer {target} sur macOS, ajoute cette règle PF :\n"
                f"```\necho '{rule}' | sudo pfctl -a phoebus -f -\nsudo pfctl -e\n```\n"
                f"Ou utilise ton routeur pour bloquer l'adresse MAC de l'appareil.")
    elif system == "Linux":
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["sudo", "iptables", "-A", "FORWARD", "-s", target, "-j", "DROP"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return f"Appareil {target} bloqué via iptables."
            return f"Erreur iptables : {result.stderr[:200]}"
        except Exception as e:
            return f"Erreur blocage : {e}"
    return f"Blocage réseau non supporté sur {system}."
