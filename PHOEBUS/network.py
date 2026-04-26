"""Découverte et contrôle du réseau LAN.

PHOEBUS doit savoir QUI est sur le réseau pour pouvoir agir : Mac de
Floriace, iPhone, smart TV, caméras, imprimantes, ESP32, prises
connectées, etc.

Trois techniques de découverte cumulées (chacune attrape ce que les
autres ratent) :

1. **mDNS / Bonjour** (`zeroconf` si installé) — détecte les services
   annoncés sur le LAN : `_airplay._tcp` (Apple TV), `_googlecast._tcp`
   (Chromecast), `_homekit._tcp`, `_printer._tcp`, `_ssh._tcp`, etc.

2. **ARP table** parsée localement (`arp -a`) — liste tous les hôtes que
   le système a déjà vus passer (rapide, pas de scan actif).

3. **Ping sweep** (asyncio + ping subprocess) — découvre les IPs réveillées
   sur le subnet local (lent mais exhaustif). Activé uniquement à la
   demande.

Actions exposées :
- network_scan         : snapshot complet (mDNS + ARP)
- network_ping_sweep   : balayage actif du subnet (peut prendre 10-30s)
- network_wake         : Wake-on-LAN d'une machine (magic packet UDP/9)
- network_ping         : ping ciblé (réveille un device, vérifie présence)
- network_who          : qui est connecté en ce moment ?

Aucune dépendance hard-required : si zeroconf n'est pas installé on se
contente d'ARP + ping.
"""
import asyncio
import ipaddress
import os
import re
import socket
import struct
import subprocess
import time
from typing import Dict, List, Optional, Set

from PHOEBUS.observability import measure


SCAN_CACHE_TTL_S = 30
_cache = {"ts": 0.0, "devices": []}


# ── Utilitaires réseau ────────────────────────────────────────────────────

def _local_ip() -> str:
    """Renvoie l'IP locale de la machine sur le LAN."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 53))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _local_subnet() -> Optional[ipaddress.IPv4Network]:
    """Subnet /24 dérivé de l'IP locale (heuristique simple mais fiable
    pour 99 % des LAN domestiques)."""
    try:
        ip = _local_ip()
        if ip == "127.0.0.1":
            return None
        return ipaddress.ip_network(f"{ip}/24", strict=False)
    except Exception:
        return None


def _normalise_mac(raw: str) -> str:
    """Format MAC compact lowercase aa:bb:cc:dd:ee:ff."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", raw or "").lower()
    if len(cleaned) != 12:
        return ""
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


# ── ARP table parsing ─────────────────────────────────────────────────────

_ARP_LINE_RE = re.compile(
    r"\(?(?P<ip>\d+\.\d+\.\d+\.\d+)\)?"           # 192.168.1.1
    r".*?"
    r"(?P<mac>[0-9A-Fa-f]{2}(?:[:\-]?[0-9A-Fa-f]{2}){5})"  # mac
)


def _parse_arp_output(text: str) -> List[dict]:
    devices = []
    for line in text.splitlines():
        m = _ARP_LINE_RE.search(line)
        if not m:
            continue
        ip = m.group("ip")
        mac = _normalise_mac(m.group("mac"))
        if not mac or mac == "00:00:00:00:00:00":
            continue
        # Nom d'hôte parfois en début de ligne (BSD/macOS).
        host = ""
        head = line.split("(")[0].strip()
        if head and head != "?" and "incomplete" not in head.lower():
            host = head.split()[0]
        devices.append({"ip": ip, "mac": mac, "hostname": host, "source": "arp"})
    # Déduplication par (ip, mac).
    seen: Set[tuple] = set()
    uniq = []
    for d in devices:
        k = (d["ip"], d["mac"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(d)
    return uniq


def scan_arp() -> List[dict]:
    """Lit la table ARP du système. Pas de paquets envoyés sur le LAN."""
    try:
        # macOS et Linux : `arp -a` fonctionne pareil.
        out = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=4
        )
        return _parse_arp_output(out.stdout or "")
    except Exception as e:
        print(f"[NET] ARP scan KO : {e}")
        return []


# ── mDNS / Bonjour discovery ─────────────────────────────────────────────

# Services typiques d'un foyer connecté.
_MDNS_SERVICES = (
    "_airplay._tcp.local.",
    "_googlecast._tcp.local.",
    "_raop._tcp.local.",          # AirPlay audio
    "_homekit._tcp.local.",
    "_hap._tcp.local.",           # HomeKit Accessory Protocol
    "_printer._tcp.local.",
    "_ipp._tcp.local.",
    "_ipps._tcp.local.",
    "_ssh._tcp.local.",
    "_sftp-ssh._tcp.local.",
    "_smb._tcp.local.",           # partage Windows/macOS
    "_spotify-connect._tcp.local.",
    "_hue._tcp.local.",           # Philips Hue
    "_esphomelib._tcp.local.",    # ESPHome
    "_workstation._tcp.local.",   # Linux/macOS workstations
    "_device-info._tcp.local.",
)


def scan_mdns(timeout_s: float = 3.0) -> List[dict]:
    """Découverte mDNS via zeroconf si dispo. Renvoie les services trouvés."""
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    except Exception:
        return []

    found: Dict[str, dict] = {}

    class _Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            try:
                info = zc.get_service_info(type_, name, timeout=1500)
                if not info:
                    return
                addresses = info.parsed_scoped_addresses() or []
                ip = addresses[0] if addresses else ""
                key = f"{name}|{ip}"
                if key in found:
                    return
                # Décode les propriétés TXT (souvent useful : modèle, version).
                props = {}
                for k, v in (info.properties or {}).items():
                    try:
                        kk = k.decode() if isinstance(k, bytes) else str(k)
                        vv = v.decode() if isinstance(v, bytes) else str(v) if v else ""
                        props[kk] = vv
                    except Exception:
                        continue
                found[key] = {
                    "ip": ip,
                    "hostname": (info.server or "").rstrip("."),
                    "service": type_.rstrip("."),
                    "name": name.rstrip("."),
                    "port": info.port,
                    "properties": props,
                    "source": "mdns",
                }
            except Exception:
                pass

        def update_service(self, zc, type_, name):
            self.add_service(zc, type_, name)

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    listener = _Listener()
    browsers = []
    try:
        for svc in _MDNS_SERVICES:
            try:
                browsers.append(ServiceBrowser(zc, svc, listener))
            except Exception:
                continue
        time.sleep(timeout_s)
    finally:
        try:
            for b in browsers:
                b.cancel()
        except Exception:
            pass
        zc.close()

    return list(found.values())


# ── Ping sweep ────────────────────────────────────────────────────────────

async def _ping_one(ip: str, timeout_s: float = 1.0) -> bool:
    """True si l'hôte répond au ping."""
    # macOS : -c count -W timeout(ms) | Linux : -c count -W timeout(s)
    if os.uname().sysname == "Darwin":
        cmd = ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout_s)), ip]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await asyncio.wait_for(proc.wait(), timeout=timeout_s + 0.5)
        return rc == 0
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return False


async def ping_sweep(subnet: Optional[str] = None, max_concurrent: int = 64) -> List[str]:
    """Balaye le subnet en parallèle. Renvoie la liste des IPs qui répondent.

    Sur un /24 typique (254 hôtes) : ~5-10 secondes avec 64 workers.
    """
    net = ipaddress.ip_network(subnet) if subnet else _local_subnet()
    if net is None:
        return []
    hosts = [str(h) for h in net.hosts()]
    sem = asyncio.Semaphore(max_concurrent)

    async def _wrap(ip):
        async with sem:
            ok = await _ping_one(ip)
            return ip if ok else None

    async with measure("network.ping_sweep"):
        results = await asyncio.gather(*[_wrap(ip) for ip in hosts])
    return [ip for ip in results if ip]


# ── Wake-on-LAN ──────────────────────────────────────────────────────────

def wake_on_lan(mac: str, broadcast: str = "255.255.255.255") -> bool:
    """Envoie un magic packet WOL au MAC indiqué.

    Ne nécessite pas de privilèges root. Pour que ça marche, la machine
    cible doit avoir Wake-on-LAN activé dans son BIOS/réglages réseau.
    """
    mac_clean = _normalise_mac(mac)
    if not mac_clean:
        print(f"[WOL] MAC invalide : {mac}")
        return False
    raw = bytes.fromhex(mac_clean.replace(":", ""))
    if len(raw) != 6:
        return False
    magic = b"\xff" * 6 + raw * 16
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # On envoie sur les 3 ports usuels (7, 9, et 40000 pour certains routeurs).
            for port in (7, 9, 40000):
                try:
                    s.sendto(magic, (broadcast, port))
                except Exception:
                    continue
        return True
    except Exception as e:
        print(f"[WOL] Envoi KO : {e}")
        return False


# ── Port scan léger (services courants seulement) ───────────────────────

_COMMON_PORTS = {
    22: "ssh", 23: "telnet", 80: "http", 443: "https",
    554: "rtsp", 1883: "mqtt", 8083: "mqtt-ws", 8123: "homeassistant",
    32400: "plex", 8009: "chromecast", 7000: "airplay",
    548: "afp", 445: "smb", 139: "netbios", 631: "ipp/cups",
    8888: "alt-http", 8080: "alt-http", 5900: "vnc",
    1900: "ssdp", 5353: "mdns",
}


async def _probe_port(ip: str, port: int, timeout_s: float = 0.4) -> bool:
    try:
        fut = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout_s)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def probe_services(ip: str) -> Dict[int, str]:
    """Sonde les ports communs d'un hôte. Renvoie {port: nom_service}."""
    async def check(p):
        return p, await _probe_port(ip, p)
    results = await asyncio.gather(*[check(p) for p in _COMMON_PORTS])
    return {p: _COMMON_PORTS[p] for p, ok in results if ok}


# ── Vue unifiée + cache ──────────────────────────────────────────────────

async def discover(refresh: bool = False, mdns_timeout: float = 2.5) -> List[dict]:
    """Vue agrégée du LAN : ARP + mDNS, dédupliquée par IP.

    Cache 30s pour éviter de spammer le réseau si on appelle plusieurs
    fois rapidement.
    """
    now = time.time()
    if not refresh and (now - _cache["ts"]) < SCAN_CACHE_TTL_S:
        return _cache["devices"]

    async with measure("network.discover"):
        arp_devices = await asyncio.to_thread(scan_arp)
        mdns_devices = await asyncio.to_thread(scan_mdns, mdns_timeout)

    # Fusion par IP : on enrichit l'entrée ARP avec les services mDNS.
    by_ip: Dict[str, dict] = {}
    for d in arp_devices:
        by_ip[d["ip"]] = {**d, "services": []}
    for s in mdns_devices:
        ip = s.get("ip")
        if not ip:
            continue
        entry = by_ip.setdefault(
            ip, {"ip": ip, "mac": "", "hostname": "", "services": [], "source": "mdns"}
        )
        if s.get("hostname") and not entry.get("hostname"):
            entry["hostname"] = s["hostname"]
        entry["services"].append(
            {
                "type": s.get("service", ""),
                "name": s.get("name", ""),
                "port": s.get("port"),
                "properties": s.get("properties", {}),
            }
        )

    devices = list(by_ip.values())
    _cache["ts"] = now
    _cache["devices"] = devices
    return devices


def label_for_device(device: dict) -> str:
    """Étiquette humaine : 'iPhone Floriace (192.168.1.42)' si possible."""
    name = device.get("hostname") or ""
    services = device.get("services") or []
    if not name and services:
        # On essaie de tirer un nom d'un service mDNS (souvent plus humain).
        name = services[0].get("name", "").split("._")[0]
    name = (name or "").strip()
    ip = device.get("ip", "")
    if name and ip:
        return f"{name} ({ip})"
    return ip or name or "appareil inconnu"
