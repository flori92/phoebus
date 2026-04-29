#!/usr/bin/env python3
"""
PHOEBUS CLI - Interface en ligne de commande pour PHOEBUS.
Permet d'envoyer des commandes texte directement au cerveau de PHOEBUS.
"""
import asyncio
import sys
import os
import argparse

# S'assurer que le script tourne dans le venv
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
venv_py = os.path.join(ROOT_DIR, ".venv", "bin", "python")
if sys.prefix == sys.base_prefix and os.path.exists(venv_py):
    os.execv(venv_py, [venv_py] + sys.argv)

try:
    from PHOEBUS.router import executer_commande_generique
except ImportError:
    print("[ERREUR] Impossible de charger PHOEBUS. Lancez depuis la racine du projet.")
    sys.exit(1)

async def run_cli():
    parser = argparse.ArgumentParser(description="PHOEBUS CLI")
    parser.add_argument("commande", nargs="*", help="La commande à envoyer à Phoebus")
    parser.add_argument("--interactive", "-i", action="store_true", help="Lancer en mode interactif")
    parser.add_argument("--voice", action="store_true", help="Activer la voix (désactivée par défaut en CLI)")
    args = parser.parse_args()

    # Désactiver la voix par défaut pour le CLI sauf si explicitement demandé
    if not args.voice:
        os.environ["PHOEBUS_MUTE"] = "1"
    source = "voix" if args.voice else "cli"

    if args.interactive or not args.commande:
        print("=== PHOEBUS CLI INTERACTIF ===")
        print("Tapez 'exit' ou 'quit' pour quitter.")
        while True:
            try:
                texte = input("\n[VOUS] > ")
                if texte.lower() in ("exit", "quit"):
                    break
                if not texte.strip():
                    continue
                
                reponse = await executer_commande_generique(texte, source=source)
                print(f"[PHOEBUS] {reponse}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[ERREUR] {e}")
    else:
        texte = " ".join(args.commande)
        reponse = await executer_commande_generique(texte, source=source)
        print(f"[PHOEBUS] {reponse}")

if __name__ == "__main__":
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        pass
