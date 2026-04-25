#!/usr/bin/env python3
"""
PHOEBUS Core Launcher
Point d'entrée principal pour lancer l'assistant PHOEBUS et son interface web.
"""
import sys
import asyncio
import os
import shutil
import subprocess
import socket
from urllib.parse import urlparse

# Dossier racine du projet
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Auto-VENV Switch ────────────────────────────────────────────────────────
def ensure_venv():
    """S'assure que le script tourne dans le venv, sinon se relance lui-même."""
    in_venv = (sys.prefix != sys.base_prefix) or hasattr(sys, 'real_prefix')
    venv_py = os.path.join(ROOT_DIR, ".venv", "bin", "python")
    if not in_venv and os.path.exists(venv_py):
        if sys.executable != venv_py:
            print(f"[SYSTEM] Passage sur l'environnement virtuel (.venv)...")
            os.execv(venv_py, [venv_py] + sys.argv)

if __name__ == "__main__":
    ensure_venv()

try:
    from PHOEBUS.server import main as PHOEBUS_main
except ImportError as e:
    print(f"[ERREUR FATALE] Impossible de charger le package 'PHOEBUS': {e}")
    print("Assurez-vous d'exécuter ce script depuis la racine du projet PHOEBUS.")
    sys.exit(1)

# ── Zeroconf (PHOEBUS.local) ──────────────────────────────────────────────────
try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    _ZEROCONF_AVAILABLE = True
except ImportError:
    _ZEROCONF_AVAILABLE = False

async def run_zeroconf_broadcast():
    """Diffuse l'alias PHOEBUS.local sur le réseau local."""
    if not _ZEROCONF_AVAILABLE:
        return

    from PHOEBUS.utils import get_lan_ip
    local_ip = get_lan_ip()
    if not local_ip or local_ip == "127.0.0.1":
        return

    print(f"[NETWORK] Diffusion de l'alias PHOEBUS.local vers {local_ip}...")
    
    desc = {'version': '1.0', 'assistant': 'PHOEBUS'}
    # Nom du service mDNS
    info = ServiceInfo(
        "_http._tcp.local.",
        "PHOEBUS._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=8080,
        properties=desc,
        server="PHOEBUS.local.",
    )

    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    try:
        zeroconf.register_service(info)
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"[NETWORK] Erreur Zeroconf : {e}")
    finally:
        try:
            zeroconf.unregister_service(info)
            zeroconf.close()
        except: pass

async def open_browser():
    """Ouvre automatiquement le navigateur vers l'interface PHOEBUS."""
    # On attend que le frontend ait eu le temps de démarrer
    await asyncio.sleep(4)
    from PHOEBUS.utils import open_uri
    
    # On privilégie phoebus.local si possible, sinon localhost
    # Note: .local nécessite mDNS fonctionnel sur la machine
    url = "http://localhost:8080"
    if _ZEROCONF_AVAILABLE:
        # On tente phoebus.local (mDNS)
        url = "http://phoebus.local:8080"
        
    print(f"[SYSTEM] Ouverture de l'interface : {url}")
    open_uri(url)

async def run_frontend():
    """Lance le serveur de développement Vite pour le frontend."""
    frontend_dir = os.path.join(ROOT_DIR, "frontend")
    if not os.path.exists(frontend_dir):
        print("[FRONTEND] Dossier frontend/ introuvable, skip.")
        return

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("[FRONTEND] npm non trouvé, impossible de lancer l'interface web.")
        return

    print("[FRONTEND] Démarrage de l'interface PHOEBUS (Vite) sur le port 8080...")
    try:
        # On crée le dossier logs s'il n'existe pas
        logs_dir = os.path.join(ROOT_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file = open(os.path.join(logs_dir, "frontend.log"), "w")

        # On lance npm run dev sur le port 8080
        process = await asyncio.create_subprocess_exec(
            npm, "run", "dev", "--", "--port", "8080", "--host", "0.0.0.0",
            cwd=frontend_dir,
            stdout=log_file,
            stderr=log_file
        )
        await process.wait()
    except Exception as e:
        print(f"[FRONTEND] Erreur lors du lancement : {e}")


def _env_mode(value, default="auto"):
    return (value if value is not None else default).strip().lower()


def _arena_url_is_local():
    raw = os.getenv("ARENA_URL", "http://localhost:8000/api/v1").strip()
    host = urlparse(raw).hostname
    return host in {None, "", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _arena_bridge_should_start():
    mode = _env_mode(os.getenv("PHOEBUS_ARENA_BRIDGE_AUTO_START"), "auto")
    if mode in {"0", "false", "no", "off", "disabled", "never"}:
        return False
    if not _arena_url_is_local():
        return False
    if mode in {"1", "true", "yes", "on", "enabled", "always"}:
        return True
    if any(os.getenv(key, "").strip() for key in ("ARENA_AUTH_PROD_V1", "ARENA_AUTH_TOKEN", "LMARENA_AUTH_TOKEN", "ARENA_COOKIE_HEADER")):
        return True
    return os.path.exists(os.path.join(ROOT_DIR, "external", "LMArenaBridge", "config.json"))


async def run_arena_bridge():
    """Lance LMArenaBridge si la configuration locale Arena est presente."""
    if not _arena_bridge_should_start():
        return

    script = os.path.join(ROOT_DIR, "scripts", "arena_bridge.py")
    if not os.path.exists(script):
        print("[ARENA] scripts/arena_bridge.py introuvable, bridge ignore.")
        return

    print("[ARENA] Verification du bridge LMArena...")
    try:
        log_path = os.getenv("PHOEBUS_ARENA_BRIDGE_LOG", os.path.join(ROOT_DIR, "logs", "arena_bridge.log"))
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "ab") as log_file:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                script,
                "start",
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            await process.wait()
    except Exception as e:
        print(f"[ARENA] Bridge indisponible : {e}")


async def main():
    frontend_dir = os.path.join(ROOT_DIR, "frontend")

    # On lance tout en parallèle
    tasks = [
        PHOEBUS_main(), 
        run_arena_bridge(),
        run_zeroconf_broadcast()
    ]

    if os.path.exists(frontend_dir):
        tasks.append(run_frontend())
        tasks.append(open_browser())

    await asyncio.gather(*tasks)
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[PHOEBUS] Arrêt du système. Au revoir Floriace.")
    except Exception as e:
        # On ignore les erreurs de socket fermée au shutdown
        if "Event loop is closed" not in str(e):
            print(f"\n[PHOEBUS] Erreur critique inattendue : {e}")
