# PHOEBUS/actions.py
"""Exécuteur d'actions de PHOEBUS. Pilote les skills et les fonctions système."""
import asyncio
import os
import PHOEBUS.state as state
from PHOEBUS.voice import parler
from PHOEBUS.skills import is_skill_registered, execute_skill

async def executer_une_action(d, *, speak: bool = True):
    """Exécute un bloc JSON d'action unique en utilisant le Skill Registry."""
    action = d.get("action")
    if not action:
        return ""

    # 1. Utilisation du Registre de Skills (Architecture PHOEBUS 3.0)
    # Toutes les capacités (HA, Spotify, Google, Système, etc.) sont désormais ici.
    if is_skill_registered(action):
        ok, msg = await execute_skill(action, d)
        if msg and speak:
            await parler(msg)
        return msg or ""

    # 2. Fallback pour les actions système résiduelles non encore migrées
    if action == "redemarrer_phoebus":
        msg = "À vos ordres. Je me relance."
        if speak:
            await parler(msg)
        await asyncio.sleep(1.5)
        import sys
        sys.exit(42)

    elif action == "mode_interprete":
        state.INTERPRETE_ACTIF = (d.get("etat") == "on")
        state.INTERPRETE_LANGUE_CIBLE = d.get("langue", "anglais")
        msg = f"Mode interprète {'activé' if state.INTERPRETE_ACTIF else 'désactivé'}."
        if speak:
            await parler(msg)
        return msg
        
    else:
        print(f"[ACTIONS] Action non reconnue ou non migrée : {action}")
        return ""
