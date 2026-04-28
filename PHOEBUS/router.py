"""PHOEBUS Router Central — Unifie le flux des requêtes.
Texte → Intent → Sécurité → Skill → Réponse.
"""
import asyncio
import json
import time
from typing import Optional, Any

import PHOEBUS.state as state
from PHOEBUS.config import WS_AUTH_REQUIRED
from PHOEBUS.intent import detect as detect_intent
from PHOEBUS.ai import demander_ia, demander_ia_stream
from PHOEBUS.audio_optimization import check_hallucination

async def route_request(
    texte: str,
    source: str = "voice",
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    on_sentence: Optional[Any] = None,
) -> str:
    """Route une requête utilisateur vers le bon moteur d'exécution."""
    if not texte or not texte.strip():
        return ""

    # 1. Nettoyage et vérification hallucination
    texte = texte.strip()
    if source == "voice":
        is_hallucination, confidence = check_hallucination(texte)
        if is_hallucination:
            print(f"[ROUTER] Hallucination détectée ({confidence:.2f}) : '{texte}' → Rejet.")
            return ""

    print(f"[ROUTER] Traitement requête ({source}) : '{texte}'")

    # 2. Gérer confirmation en attente
    if state.PENDING_CONFIRMATION:
        # La logique de confirmation sera migrée ici plus tard
        pass

    # 3. Fast-path Intent local
    intent = detect_intent(texte)
    if intent is not None:
        print(f"[ROUTER] Fast-path local : {intent.name}")
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", intent.reply)
        if on_sentence:
            await on_sentence(intent.reply)
        return intent.reply

    # 4. Intelligence Cloud / Hybride
    if on_sentence:
        # Mode streaming si supporté
        reponse_complete = await demander_ia_stream(texte, on_sentence=on_sentence)
    else:
        reponse_complete = await demander_ia(texte)

    # 5. Extraction et exécution des actions JSON
    # La fonction executer_commande_generique s'en charge déjà dans ai.py
    # mais nous allons progressivement centraliser cela ici.

    return reponse_complete
