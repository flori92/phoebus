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
from urllib.parse import urlparse

# ── Auto-VENV Switch ────────────────────────────────────────────────────────
def ensure_venv():
    """S'assure que le script tourne dans le venv, sinon se relance lui-même."""
    # Détection robuste du venv
    in_venv = (sys.prefix != sys.base_prefix) or hasattr(sys, 'real_prefix')
    
    venv_py = os.path.join(os.getcwd(), ".venv", "bin", "python")
    
    # Si on n'est pas dans le venv et qu'il existe, on relance
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

async def run_frontend():
    """Lance le serveur de développement Vite pour le frontend."""
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    if not os.path.exists(frontend_dir):
        print("[FRONTEND] Dossier frontend/ introuvable, skip.")
        return

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("[FRONTEND] npm non trouvé, impossible de lancer l'interface web.")
        return

    print("[FRONTEND] Démarrage de l'interface (Vite)...")
    try:
        # On lance npm run dev en tâche de fond
        process = await asyncio.create_subprocess_exec(
            npm, "run", "dev", "--", "--port", "5173", "--host", "0.0.0.0",
            cwd=frontend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
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
    return os.path.exists(os.path.join(os.getcwd(), "external", "LMArenaBridge", "config.json"))


async def run_arena_bridge():
    """Lance LMArenaBridge si la configuration locale Arena est presente."""
    if not _arena_bridge_should_start():
        return

    script = os.path.join(os.getcwd(), "scripts", "arena_bridge.py")
    if not os.path.exists(script):
        print("[ARENA] scripts/arena_bridge.py introuvable, bridge ignore.")
        return

    print("[ARENA] Verification du bridge LMArena...")
    try:
        log_path = os.getenv("PHOEBUS_ARENA_BRIDGE_LOG", os.path.join("logs", "arena_bridge.log"))
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
    # On lance le backend et le frontend en parallèle
    # PHOEBUS_main() est une fonction asynchrone qui contient déjà sa propre boucle infinie
    tasks = [PHOEBUS_main(), run_arena_bridge()]
    
    # On ne lance le frontend que si on n'est pas dans un environnement de prod restreint
    if os.path.exists("frontend"):
        tasks.append(run_frontend())
        
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[PHOEBUS] Arrêt du système. Au revoir Floriace.")
    except Exception as e:
        print(f"\n[PHOEBUS] Erreur critique inattendue : {e}")
