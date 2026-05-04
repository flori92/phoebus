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
from PHOEBUS.command_result import CommandResult, new_trace_id
from PHOEBUS.observability import record_request, record_trace_event

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


def _confirmation_prompt(payload: dict[str, Any]) -> str:
    action = payload.get("action", "")
    try:
        from PHOEBUS.skills import is_skill_registered, describe_skill
        desc = describe_skill(action, payload) if is_skill_registered(action) else describe_action(payload)
    except Exception:
        desc = describe_action(payload)
    return f"Confirmation requise : {desc}. Répondez 'je confirme' ou 'annule'."


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

async def executer_commande(texte: str, source: str = "voix", metadata: dict = None) -> CommandResult:
    """Exécute une commande et renvoie un résultat structuré indépendant du canal."""
    trace_id = new_trace_id()
    result = CommandResult(source=source, trace_id=trace_id, metadata=metadata or {})
    if not texte:
        result.status = "empty"
        result.text = ""
        return result

    request_started = time.perf_counter()
    text_only = source in {"telegram", "cli"}
    
    state.mark_user_activity()
    meta_str = ""
    if metadata:
        m = metadata
        meta_str = f" [Batt: {m.get('battery')}% | Loc: {m.get('location')} | Focus: {m.get('focus')}]"
    
    print(f"[ROUTER:{source.upper()}:{trace_id}{meta_str}] {texte}")
    record_trace_event(trace_id, "command.start", source=source, text_len=len(texte or ""))

    full_text_parts = []
    spoken = {"v": False}
    speech = _SpeechQueue()

    if state.PENDING_CONFIRMATION:
        pending = state.PENDING_CONFIRMATION
        if is_cancellation_text(texte):
            state.PENDING_CONFIRMATION = None
            audit_log("sensitive_action_cancelled", action=pending.get("action"))
            msg = "Action annulée, Monsieur."
            if not text_only:
                await _parler_safe(msg)
            result.text = msg
            result.status = "cancelled"
            record_trace_event(trace_id, "confirmation.cancelled", action=pending.get("action"))
            return result
        if is_confirmation_text(texte):
            state.PENDING_CONFIRMATION = None
            audit_log("sensitive_action_confirmed", action=pending.get("action"))
            if not text_only:
                await _parler_safe("Action confirmée, Floriace. J'exécute.")
            from PHOEBUS.actions import executer_une_action
            ok, msg = await executer_une_action(pending, speak=not text_only)
            if not ok:
                # Tentative d'auto-guérison si confirmation échouée
                fallback = resolve_after_ai_failure(texte, msg)
                if fallback:
                    ok, msg = await executer_une_action(fallback.payload, speak=not text_only)
            
            if msg:
                result.action_messages.append(msg)
            result.actions.append({"action": pending.get("action", "")})
            result.text = msg or "Action confirmée, Monsieur."
            result.status = "confirmed" if ok else "failed_after_confirmation"
            record_trace_event(trace_id, "confirmation.confirmed", action=pending.get("action"), success=ok)
            return result
        msg = _confirmation_prompt(pending)
        if not text_only:
            await _parler_safe(msg)
        result.text = msg
        result.status = "confirmation_waiting"
        result.confirmation_required = True
        result.pending_action = pending
        return result
    
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
        if not text_only:
            await speech.say(s)

    # On marque le début de la réflexion
    await state.set_thinking(True)
    try:
        rep_finale_ia = await asyncio.wait_for(
            route_request(query_enrichie, source=source, metadata=metadata, on_sentence=_on_sentence),
            timeout=AI_COMMAND_TIMEOUT,
        )
        record_trace_event(
            trace_id,
            "route.done",
            response_len=len(rep_finale_ia or ""),
            streamed=bool(spoken["v"]),
        )

        if not rep_finale_ia:
            # Si route_request a retourné "" (hallucination ou vide), on reste discret
            # pour ne pas polluer l'ambiance avec des "Pardon ?".
            result.text = ""
            result.status = "empty_response"
            return result

        if "{" in (rep_finale_ia or "") and "}" in (rep_finale_ia or ""):
            action_messages: list[str] = []
            await traiter_reponse_ia(
                rep_finale_ia,
                speak=not text_only,
                action_messages=action_messages,
                trace_id=trace_id,
            )
            result.action_messages.extend(action_messages)
            if state.PENDING_CONFIRMATION:
                result.text = _confirmation_prompt(state.PENDING_CONFIRMATION)
                result.status = "confirmation_required"
                result.confirmation_required = True
                result.pending_action = state.PENDING_CONFIRMATION
                return result
            if action_messages and text_only:
                result.text = "\n".join(action_messages)
            else:
                result.text = "Action exécutée, Monsieur." if not spoken["v"] else " ".join(full_text_parts)
            result.status = "action_executed"
            return result

        if not spoken["v"] and rep_finale_ia:
            if not await traiter_reponse_ia(rep_finale_ia, speak=not text_only, trace_id=trace_id):
                if not text_only:
                    await speech.say(rep_finale_ia)
                result.text = rep_finale_ia
                return result

        result.text = " ".join(full_text_parts).strip() or rep_finale_ia or ""
        return result

    except asyncio.TimeoutError:
        result.ok = False
        result.status = "timeout"
        # Message unifié et plus pro
        msg = "Je poursuis ma réflexion, Floriace. La tâche est complexe, mais je reste sur le coup."
        if not text_only:
            await speech.say(msg)
        result.text = msg
        record_trace_event(trace_id, "command.timeout", timeout_s=AI_COMMAND_TIMEOUT)
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", msg)
        return result
    except Exception as e:
        result.ok = False
        result.status = "error"
        print(f"[ROUTER] Erreur traitement {source} : {e}")
        msg = "J'ai eu un raté interne, Floriace, mais je reste opérationnel."
        if not text_only:
            await speech.say(msg)
        result.text = msg
        record_trace_event(trace_id, "command.error", error=type(e).__name__)
        return result
    finally:
        # Fin de la réflexion (peu importe le résultat)
        await state.set_thinking(False)
        result.duration_ms = (time.perf_counter() - request_started) * 1000
        record_request(
            source=source,
            duration_ms=result.duration_ms,
            ok=result.ok,
            text_len=len(texte or ""),
            trace_id=result.trace_id,
            status=result.status,
        )
        record_trace_event(
            trace_id,
            "command.end",
            ok=result.ok,
            status=result.status,
            duration_ms=round(result.duration_ms, 1),
            reply_len=len(result.reply_text()),
        )
        state.extend_conversation()
        speech.close()


async def executer_commande_generique(texte: str, source: str = "voix", metadata: dict = None) -> str:
    """Compatibilité historique : renvoie uniquement le texte final."""
    result = await executer_commande(texte, source=source, metadata=metadata)
    return result.reply_text()

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

    # --- OPTIMISATION RADICALE : Court-circuit pour la conversation ---
    if decision.route == "chat":
        from PHOEBUS.ai import demander_ia
        print(f"[ROUTER] Route conversationnelle directe (bypass brain)")
        return await demander_ia(texte)

    # Intelligence Cloud / Hybride / Modular v2
    from PHOEBUS.core.brain import PhoebusBrain
    
    # On utilise une instance persistante pour éviter de recompiler le graphe à chaque fois
    if not hasattr(route_request, "_brain"):
        route_request._brain = PhoebusBrain()
    
    rep = await route_request._brain.think(texte, metadata=metadata)

    fallback = resolve_after_ai_failure(texte, rep or "")
    if fallback is not None:
        print(f"[ROUTER] Fallback objectif : {fallback.name} ({fallback.reason})")
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", fallback.reply)
        return fallback.reply
    return rep

async def traiter_reponse_ia(
    reponse: str,
    _request_id: str | None = None,
    speak: bool = True,
    action_messages: list[str] | None = None,
    trace_id: str | None = None,
) -> bool:
    """Analyse la réponse de l'IA, extrait le JSON et exécute les actions."""
    if not reponse: return False

    async def _emit(texte: str) -> None:
        if speak:
            await parler(texte)

    try:
        # 1. Gestion des confirmations en attente
        if state.PENDING_CONFIRMATION:
            if is_confirmation_text(reponse):
                await _emit("Action confirmée, Floriace. J'exécute.")
                d = state.PENDING_CONFIRMATION
                state.PENDING_CONFIRMATION = None
                audit_log("sensitive_action_confirmed", action=d.get("action"))
                from PHOEBUS.actions import executer_une_action
                msg = await executer_une_action(d, speak=speak)
                if msg and action_messages is not None:
                    action_messages.append(msg)
                if trace_id:
                    record_trace_event(trace_id, "action.executed", action=d.get("action"), confirmed=True)
                return True
            elif is_cancellation_text(reponse):
                await _emit("Action annulée, Monsieur.")
                audit_log("sensitive_action_cancelled", action=state.PENDING_CONFIRMATION.get("action"))
                state.PENDING_CONFIRMATION = None
                return True
            else:
                await _emit("En attente de votre confirmation. Dites 'PHOEBUS je confirme' ou 'Annule'.")
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
                    if trace_id:
                        record_trace_event(trace_id, "action.detected", action=action)
                    verdict = guard.check(d)
                    if verdict.blocked:
                        audit_log("action_loop_blocked", action=action, reason=verdict.reason)
                        await _emit("Je bloque une répétition d'action pour éviter une boucle.")
                        if trace_id:
                            record_trace_event(trace_id, "action.blocked", action=action, reason=verdict.reason)
                        continue

                    risk = risk_level_for(action)
                    desc = describe_skill(action, d) if is_skill_registered(action) else describe_action(d)

                    if risk == "high":
                        await _emit(f"Vous me demandez de {desc}. C'est une action sensible, vous confirmez ?")
                        state.PENDING_CONFIRMATION = d
                        audit_log("sensitive_action_pending", action=action, description=desc, risk=risk)
                        if trace_id:
                            record_trace_event(trace_id, "action.confirmation_required", action=action, risk=risk)
                        return True

                    if risk == "medium":
                        await _emit(f"J'applique : {desc}.")
                        await asyncio.sleep(1.2)
                        if state.STOP_PARLER:
                            state.STOP_PARLER = False
                            await _emit("D'accord, j'annule.")
                            audit_log("medium_action_aborted", action=action, description=desc)
                            if trace_id:
                                record_trace_event(trace_id, "action.aborted", action=action)
                            continue
                        audit_log("medium_action_executed", action=action, description=desc)
                        ok, msg = await executer_une_action(d, speak=speak)
                    else:
                        ok, msg = await executer_une_action(d, speak=speak)
                    
                    if not ok:
                        # --- AUTO-GUÉRISON (Self-Healing) ---
                        print(f"[ROUTER] Action {action} échouée. Tentative d'auto-guérison...")
                        # On ré-analyse l'intention initiale pour trouver un fallback
                        # Note: on utilise la reponse d'erreur comme trigger
                        fallback = resolve_after_ai_failure(texte, msg)
                        if fallback and fallback.payload.get("action") != action:
                            print(f"[ROUTER] Auto-guérison : repli sur {fallback.name}")
                            await _emit("Je rencontre une difficulté, je tente une autre approche.")
                            ok, msg = await executer_une_action(fallback.payload, speak=speak)

                    if msg and action_messages is not None:
                        action_messages.append(msg)
                    if trace_id:
                        record_trace_event(trace_id, "action.executed", action=action, risk=risk, success=ok)
                return True

        # 3. Réponse naturelle
        if len(reponse.strip()) > 2:
            stocker_souvenir(f"PHOEBUS a dit : {reponse}", source="conversation", importance=1)
            await _emit(reponse)
            return True

    except Exception as e:
        print(f"[ROUTER] Erreur traitement IA : {e}")
        await _emit("Il y a eu un petit raté dans mon interprétation, Monsieur.")

    return False
