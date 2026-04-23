#!/usr/bin/env python3
"""
JARVIS Core Launcher
Point d'entrée principal pour lancer l'assistant JARVIS refactorisé.
"""
import sys
import asyncio

try:
    from jarvis.server import main
except ImportError as e:
    print(f"[ERREUR FATALE] Impossible de charger le package 'jarvis': {e}")
    print("Assurez-vous d'exécuter ce script depuis la racine du projet Jarvis.")
    sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JARVIS] Arrêt du système. Au revoir Floriace.")
    except Exception as e:
        print(f"\n[JARVIS] Erreur critique inattendue : {e}")
