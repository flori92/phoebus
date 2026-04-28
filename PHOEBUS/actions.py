# PHOEBUS/actions.py
"""Exécuteur d'actions de PHOEBUS. Pilote les skills et les fonctions système."""
import asyncio
import os
import PHOEBUS.state as state
from PHOEBUS.voice import parler
from PHOEBUS.skills import is_skill_registered, execute_skill

async def executer_une_action(d):
    """Exécute un bloc JSON d'action unique en utilisant le Skill Registry."""
    action = d.get("action")
    if not action:
        return

    # 1. Utilisation du Registre de Skills (Architecture PHOEBUS 3.0)
    # Toutes les capacités (HA, Spotify, Google, Système, etc.) sont désormais ici.
    if is_skill_registered(action):
        ok, msg = await execute_skill(action, d)
        if msg:
            await parler(msg)
        return

    # 2. Fallback pour les actions système résiduelles non encore migrées
    if action == "redemarrer_phoebus":
        await parler("À vos ordres. Je me relance.")
        await asyncio.sleep(1.5)
        import sys
        sys.exit(42)

    elif action == "mode_interprete":
        state.INTERPRETE_ACTIF = (d.get("etat") == "on")
        state.INTERPRETE_LANGUE_CIBLE = d.get("langue", "anglais")
        await parler(f"Mode interprète {'activé' if state.INTERPRETE_ACTIF else 'désactivé'}.")
        
    else:
        print(f"[ACTIONS] Action non reconnue ou non migrée : {action}")
