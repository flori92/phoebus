#!/usr/bin/env python3
"""
JARVIS Core Launcher
Point d'entrée principal pour lancer l'assistant JARVIS et son interface web.
"""
import sys
import asyncio
import os
import shutil
import subprocess

try:
    from jarvis.server import main as jarvis_main
except ImportError as e:
    print(f"[ERREUR FATALE] Impossible de charger le package 'jarvis': {e}")
    print("Assurez-vous d'exécuter ce script depuis la racine du projet Jarvis.")
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

async def main():
    # On lance le backend et le frontend en parallèle
    # jarvis_main() est une fonction asynchrone qui contient déjà sa propre boucle infinie
    tasks = [jarvis_main()]
    
    # On ne lance le frontend que si on n'est pas dans un environnement de prod restreint
    if os.path.exists("frontend"):
        tasks.append(run_frontend())
        
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JARVIS] Arrêt du système. Au revoir Floriace.")
    except Exception as e:
        print(f"\n[JARVIS] Erreur critique inattendue : {e}")
