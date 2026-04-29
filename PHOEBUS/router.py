"""PHOEBUS Router Central — Unifie le flux des requêtes.
Texte → Intent → Sécurité → Skill → Réponse.
"""
import asyncio
import json
import os
import time
from typing import Optional, Any

import PHOEBUS.state as state
from PHOEBUS.ai import demander_ia, demander_ia_stream
from PHOEBUS.audio_optimization import check_hallucination
from PHOEBUS.voice import parler
from PHOEBUS.security import audit_log, risk_level_for, describe_action, is_confirmation_text, is_cancellation_text
from PHOEBUS.rag_memory import stocker_souvenir
from PHOEBUS.natural_goals import resolve_after_ai_failure
from PHOEBUS.action_guard import ActionSequenceGuard
from PHOEBUS.routing_policy import decide_route
from PHOEBUS.observability import record_request

# Constantes de délai
AI_COMMAND_TIMEOUT = float(os.getenv("PHOEBUS_AI_COMMAND_TIMEOUT", "35.0"))


def _extraire_jsons_de_reponse(texte: str) -> list[dict[str, Any]]:
    """Extrait les objets JSON présents dans une réponse texte ou Markdown."""
    if not texte or "{" not in texte:
        return []

    decoder = json.JSONDecoder()
    objets = []
    index = 0
    while index < len(texte):
        start = texte.find("{", index)
        if start == -1:
            break
        try:
            parsed, end = decoder.raw_decode(texte[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(parsed, dict):
            objets.append(parsed)
        index = start + max(end, 1)
    return objets


def extraire_json_de_reponse(texte: str) -> dict[str, Any] | None:
    """Retourne le premier objet JSON trouvé dans une réponse IA."""
    objets = _extraire_jsons_de_reponse(texte)
    return objets[0] if objets else None


async def _parler_safe(texte: str, keep_conversation: bool = True) -> None:
    try:
        await parler(texte, keep_conversation=keep_conversation)
    except Exception as e:
        print(f"[VOICE] parole ignorée après erreur : {e}")

class _SpeechQueue:
    """File de parole non bloquante: le LLM continue pendant que PHOEBUS parle."""
    def __init__(self):
        self._queue = asyncio.Queue()
        self._task = None

    async def say(self, texte: str) -> None:
        if not texte or not texte.strip():
            return
        if self._task is None:
            self._task = asyncio.create_task(self._run())
        self._queue.put_nowait(texte)

    async def _run(self) -> None:
        while True:
            texte = await self._queue.get()
            if texte is None:
                self._queue.task_done()
                return
            try:
                await _parler_safe(texte)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._queue.put_nowait(None)

async def executer_commande_generique(texte: str, source: str = "voix", metadata: dict = None) -> str:
    """Exécute une commande texte et renvoie la réponse textuelle finale."""
    if not texte: return ""
    request_started = time.perf_counter()
    request_ok = True
    
    state.mark_user_activity()
    meta_str = ""
    if metadata:
        m = metadata
        meta_str = f" [Batt: {m.get('battery')}% | Loc: {m.get('location')} | Focus: {m.get('focus')}]"
    
    print(f"[ROUTER:{source.upper()}{meta_str}] {texte}")

    full_text_parts = []
    spoken = {"v": False}
    speech = _SpeechQueue()

    if state.PENDING_CONFIRMATION:
        pending = state.PENDING_CONFIRMATION
        if is_cancellation_text(texte):
            state.PENDING_CONFIRMATION = None
            audit_log("sensitive_action_cancelled", action=pending.get("action"))
            msg = "Action annulée, Monsieur."
            await _parler_safe(msg)
            return msg
        if is_confirmation_text(texte):
            state.PENDING_CONFIRMATION = None
            audit_log("sensitive_action_confirmed", action=pending.get("action"))
            await _parler_safe("Action confirmée, Floriace. J'exécute.")
            from PHOEBUS.actions import executer_une_action
            await executer_une_action(pending)
            return "Action confirmée, Monsieur."
        msg = "En attente de votre confirmation. Dites 'Phoebus je confirme' ou 'annule'."
        await _parler_safe(msg)
        return msg
    
    contexte_ios = ""
    if metadata:
        contexte_ios = (
            f"\n[INFO APPAREIL] Batterie: {metadata.get('battery')}% | "
            f"Position: {metadata.get('location')} | "
            f"Mode de concentration: {metadata.get('focus')}\n"
        )

    query_enrichie = contexte_ios + texte

    async def _on_sentence(s):
        spoken["v"] = True
        full_text_parts.append(s)
        await speech.say(s)

    try:
        rep_finale_ia = await asyncio.wait_for(
            route_request(query_enrichie, source=source, metadata=metadata, on_sentence=_on_sentence),
            timeout=AI_COMMAND_TIMEOUT,
        )

        if not rep_finale_ia:
            # Si route_request a retourné "" (hallucination ou vide), on reste discret
            # pour ne pas polluer l'ambiance avec des "Pardon ?".
            return ""

        if "{" in (rep_finale_ia or "") and "}" in (rep_finale_ia or ""):
            await traiter_reponse_ia(rep_finale_ia)
            if state.PENDING_CONFIRMATION:
                return "Confirmation requise, Monsieur."
            return "Action exécutée, Monsieur." if not spoken["v"] else " ".join(full_text_parts)

        if not spoken["v"] and rep_finale_ia:
            if not await traiter_reponse_ia(rep_finale_ia):
                await speech.say(rep_finale_ia)
                return rep_finale_ia

        return " ".join(full_text_parts).strip() or rep_finale_ia or ""

    except asyncio.TimeoutError:
        request_ok = False
        msg = "Je réfléchis encore, Floriace. La réponse vocale arrive dès que le cerveau se débloque."
        await speech.say(msg)
        return msg
    except Exception as e:
        request_ok = False
        print(f"[ROUTER] Erreur traitement {source} : {e}")
        msg = "J'ai eu un raté interne, Floriace, mais je reste opérationnel."
        await speech.say(msg)
        return msg
    finally:
        record_request(
            source=source,
            duration_ms=(time.perf_counter() - request_started) * 1000,
            ok=request_ok,
            text_len=len(texte or ""),
        )
        state.extend_conversation()
        speech.close()

async def route_request(
    texte: str,
    source: str = "voice",
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    on_sentence: Optional[Any] = None,
) -> str:
    """Route une requête utilisateur vers le bon moteur (Intent ou IA)."""
    if not texte or not texte.strip():
        return ""

    if source in ("voice", "voix"):
        is_hallucination, confidence = check_hallucination(texte)
        if is_hallucination:
            print(f"[ROUTER] Hallucination rejetée ({confidence:.2f}) : '{texte}'")
            return ""

    decision = decide_route(texte, source=source)
    print(f"[ROUTER] Route : {decision.route} ({decision.reason}, c={decision.confidence:.2f})")

    if decision.route == "simple" and decision.reply:
        print(f"[ROUTER] Fast-path local : {decision.intent_name}")
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", decision.reply)
        if on_sentence and "{" not in decision.reply:
            await on_sentence(decision.reply)
        return decision.reply

    if decision.payload is not None:
        print(f"[ROUTER] Objectif déterministe : {decision.route} ({decision.reason})")
        reply = decision.reply or json.dumps(decision.payload, ensure_ascii=False)
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", reply)
        return reply

    # Intelligence Cloud / Hybride
    if on_sentence:
        rep = await demander_ia_stream(texte, on_sentence=on_sentence)
    else:
        rep = await demander_ia(texte)

    fallback = resolve_after_ai_failure(texte, rep or "")
    if fallback is not None:
        print(f"[ROUTER] Fallback objectif : {fallback.name} ({fallback.reason})")
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", fallback.reply)
        return fallback.reply
    return rep

async def traiter_reponse_ia(reponse: str, _request_id: str | None = None) -> bool:
    """Analyse la réponse de l'IA, extrait le JSON et exécute les actions."""
    if not reponse: return False

    try:
        # 1. Gestion des confirmations en attente
        if state.PENDING_CONFIRMATION:
            if is_confirmation_text(reponse):
                await parler("Action confirmée, Floriace. J'exécute.")
                d = state.PENDING_CONFIRMATION
                state.PENDING_CONFIRMATION = None
                audit_log("sensitive_action_confirmed", action=d.get("action"))
                from PHOEBUS.actions import executer_une_action
                await executer_une_action(d)
                return True
            elif is_cancellation_text(reponse):
                await parler("Action annulée, Monsieur.")
                audit_log("sensitive_action_cancelled", action=state.PENDING_CONFIRMATION.get("action"))
                state.PENDING_CONFIRMATION = None
                return True
            else:
                await parler("En attente de votre confirmation. Dites 'PHOEBUS je confirme' ou 'Annule'.")
                return True

        # 2. Extraction JSON robuste
        if "{" in reponse and "}" in reponse:
            stocker_souvenir(f"Action JSON demandée : {reponse}", source="system", importance=2)
            
            parties = _extraire_jsons_de_reponse(reponse)
            
            if parties:
                from PHOEBUS.skills import is_skill_registered, describe_skill
                from PHOEBUS.actions import executer_une_action
                guard = ActionSequenceGuard()
                
                for d in parties:
                    action = d.get("action", "")
                    verdict = guard.check(d)
                    if verdict.blocked:
                        audit_log("action_loop_blocked", action=action, reason=verdict.reason)
                        await parler("Je bloque une répétition d'action pour éviter une boucle.")
                        continue

                    risk = risk_level_for(action)
                    desc = describe_skill(action, d) if is_skill_registered(action) else describe_action(d)

                    if risk == "high":
                        await parler(f"Vous me demandez de {desc}. C'est une action sensible, vous confirmez ?")
                        state.PENDING_CONFIRMATION = d
                        audit_log("sensitive_action_pending", action=action, description=desc, risk=risk)
                        return True

                    if risk == "medium":
                        await parler(f"J'applique : {desc}.")
                        await asyncio.sleep(1.2)
                        if state.STOP_PARLER:
                            state.STOP_PARLER = False
                            await parler("D'accord, j'annule.")
                            audit_log("medium_action_aborted", action=action, description=desc)
                            continue
                        audit_log("medium_action_executed", action=action, description=desc)
                        await executer_une_action(d)
                    else:
                        await executer_une_action(d)
                return True

        # 3. Réponse naturelle
        if len(reponse.strip()) > 2:
            stocker_souvenir(f"PHOEBUS a dit : {reponse}", source="conversation", importance=1)
            await parler(reponse)
            return True

    except Exception as e:
        print(f"[ROUTER] Erreur traitement IA : {e}")
        await parler("Il y a eu un petit raté dans mon interprétation, Monsieur.")

    return False
