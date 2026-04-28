"""Agent planificateur avec ReAct + auto-critique.

Contrairement à `agent.orchestrer_agent_autonome` qui est un ReAct basique
(action → résultat → action…), ce planner suit un vrai cycle :

    1. Plan      : le LLM produit un plan structuré (3-8 étapes).
    2. Execute   : on exécute chaque étape séquentiellement.
    3. Verify    : après chaque étape, on demande au LLM si c'est un succès.
    4. Replan    : en cas d'échec, on replanifie à partir de l'état courant.
    5. Summarize : rapport final clair.

Utile pour les demandes complexes multi-étapes : "prépare un rapport sur
la consommation d'énergie du mois, sauvegarde-le dans un Google Doc et
envoie-le à Julie".

Chaque étape du plan est elle-même un JSON d'action (même grammaire que
le dispatcher standard) → on réutilise `executer_une_action` pour exécuter.
"""
import asyncio
import json
from typing import List, Optional

from PHOEBUS.config import client, types, MODELS_LIST
from PHOEBUS.llm_health import skip as llm_skip, record_failure as llm_fail, record_success as llm_ok
from PHOEBUS.observability import measure
from PHOEBUS.security import audit_log
from PHOEBUS.action_guard import ActionSequenceGuard


# Plafonds de sécurité anti-boucle infinie.
MAX_STEPS = 8
MAX_REPLANS = 2


PLANNER_PROMPT = """Tu es le planificateur interne de Jarvis. Tu reçois une
demande complexe de Floriace et tu dois produire un PLAN d'exécution en
étapes JSON, puis le corriger si besoin.

Tu connais ces actions (liste non exhaustive) :
  ha_lumiere, ha_prise, ha_temperature, ha_thermostat, ha_scene, ha_alarme,
  meteo, recherche_web, create_doc, write_doc, create_sheet, send_email,
  media_recommendations,
  read_emails, read_calendar, timer_set, shell (via agent natif),
  ouvrir_dossier, lister_dossier, chercher_fichier.

RÉPONDS UNIQUEMENT AVEC UN JSON STRICT de la forme :

{
  "plan": [
    {"step": 1, "action": "<nom_action>", "args": { ... }, "why": "courte justification"},
    {"step": 2, "action": "...", "args": { ... }, "why": "..."},
    ...
  ],
  "summary": "phrase courte décrivant l'objectif global"
}

Contraintes :
- Maximum 8 étapes.
- Si la demande est triviale (1 seule action), renvoie un plan à 1 étape.
- Si la demande est impossible ou mal comprise, renvoie :
    {"plan": [], "summary": "raison claire"}
- Ne pose aucune question, n'écris aucun texte hors du JSON.
"""


CRITIQUE_PROMPT = """Tu es le vérificateur interne de Jarvis. L'étape
suivante vient d'être exécutée :

ÉTAPE : {step}
RÉSULTAT : {result}

OBJECTIF GLOBAL : {goal}

Renvoie un JSON strict :
{{
  "ok": true|false,
  "reason": "raison concise",
  "continue": true|false   // si true, on passe à l'étape suivante comme prévu ;
                           // si false + ok==false → on replanifie
}}

Sois tolérant : si l'action a atteint son but même différemment, `ok: true`.
"""


async def _ask_planner(instruction: str) -> dict:
    """Demande un plan au LLM. Renvoie le dict parsé ou un plan vide en cas d'échec."""
    if not client or not types:
        return {"plan": [], "summary": "planner indisponible (Gemini absent)"}
    if llm_skip("gemini"):
        return {"plan": [], "summary": "planner indisponible (Gemini en cooldown)"}

    prompt = PLANNER_PROMPT
    user_msg = f"Demande de Floriace : {instruction}"

    async with measure("planner.plan"):
        last_err = None
        for model_name in MODELS_LIST:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content, model=model_name,
                        config=types.GenerateContentConfig(
                            system_instruction=prompt, temperature=0.2,
                        ),
                        contents=[types.Content(role="user", parts=[types.Part(text=user_msg)])],
                    ),
                    timeout=15.0,
                )
                text = response.text or ""
                llm_ok("gemini")
                return _extract_json(text)
            except Exception as e:
                last_err = e
                continue
        if last_err:
            llm_fail("gemini", last_err)
    return {"plan": [], "summary": f"planner KO : {last_err}"}


async def _ask_critic(step: dict, result: str, goal: str) -> dict:
    """Critique de l'étape. Renvoie {ok, reason, continue}."""
    if not client or not types or llm_skip("gemini"):
        # Sans critique LLM, on accepte par défaut et on continue.
        return {"ok": True, "reason": "pas de critique (LLM indispo)", "continue": True}
    prompt = CRITIQUE_PROMPT.format(
        step=json.dumps(step, ensure_ascii=False),
        result=(result or "")[:500],
        goal=goal[:200],
    )
    async with measure("planner.critique"):
        last_err = None
        for model_name in MODELS_LIST:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content, model=model_name,
                        config=types.GenerateContentConfig(temperature=0.1),
                        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    ),
                    timeout=10.0,
                )
                return _extract_json(response.text or "")
            except Exception as e:
                last_err = e
                continue
        if last_err:
            llm_fail("gemini", last_err)
    return {"ok": True, "reason": "pas de critique", "continue": True}


def _extract_json(text: str) -> dict:
    """Extrait le premier objet JSON valide du texte. Tolérant aux ```json``` wrappers."""
    if not text:
        return {}
    s = text.strip()
    # Dépouille les fences markdown.
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # Premier { ... } équilibré (ignore les accolades dans les chaînes).
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, c in enumerate(s):
        if escape:
            escape = False
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(s[start:i + 1])
                except Exception:
                    return {}
    return {}


async def _run_step(step: dict) -> str:
    """Exécute une étape via le dispatcher standard. Renvoie un résumé texte."""
    # Import paresseux pour éviter la dépendance circulaire au chargement.
    from PHOEBUS.actions import executer_une_action

    action = step.get("action")
    args = step.get("args") or {}
    payload = {"action": action, **args}
    try:
        async with measure(f"planner.step.{action}"):
            await executer_une_action(payload)
        return f"Étape {step.get('step')} exécutée : {action}"
    except Exception as e:
        return f"Étape {step.get('step')} a échoué : {e}"


async def orchestrer_agent_planifie(instruction: str, parler=None) -> str:
    """Point d'entrée principal du planner.

    `parler` : coroutine optionnelle à appeler pour annoncer progression et
    résumé. Si None, reste silencieux (l'action appelante fera l'annonce).
    """
    audit_log("planner_start", instruction=instruction[:200])

    async def say(msg: str):
        if parler:
            try:
                await parler(msg)
            except Exception:
                pass

    plan_doc = await _ask_planner(instruction)
    plan: List[dict] = plan_doc.get("plan") or []
    goal = plan_doc.get("summary") or instruction

    if not plan:
        audit_log("planner_no_plan", reason=goal)
        return f"Je n'ai pas pu bâtir de plan : {goal}"

    if len(plan) > MAX_STEPS:
        plan = plan[:MAX_STEPS]

    await say(f"J'ai un plan en {len(plan)} étapes : {goal}.")

    results: List[str] = []
    replans = 0
    idx = 0
    action_guard = ActionSequenceGuard()
    while idx < len(plan):
        step = plan[idx]
        payload = {"action": step.get("action"), **(step.get("args") or {})}
        verdict = action_guard.check(payload)
        if verdict.blocked:
            audit_log("planner_action_loop_blocked", step=step.get("step"), reason=verdict.reason)
            await say("J'arrête ce plan : il répète les mêmes actions et risque de boucler.")
            break
        res = await _run_step(step)
        results.append(res)

        # Auto-critique.
        critique = await _ask_critic(step, res, goal)
        if not critique.get("ok", True):
            reason = critique.get("reason", "")
            audit_log("planner_step_failed", step=step.get("step"), reason=reason)
            if replans < MAX_REPLANS:
                replans += 1
                await say(f"Accroc à l'étape {step.get('step')} : {reason}. Je replanifie.")
                # Replan depuis l'état courant.
                history_for_replan = (
                    f"Objectif initial : {instruction}. "
                    f"Étapes déjà tentées : {json.dumps(plan[:idx+1], ensure_ascii=False)}. "
                    f"Résultats : {results}. "
                    f"Raison d'échec : {reason}. "
                    f"Propose un nouveau plan pour finir le travail."
                )
                new_doc = await _ask_planner(history_for_replan)
                new_plan = new_doc.get("plan") or []
                if new_plan:
                    plan = plan[:idx + 1] + new_plan
                    idx += 1
                    continue
                else:
                    break
            else:
                await say("Trop d'accrocs, j'arrête pour éviter de faire n'importe quoi.")
                break

        if not critique.get("continue", True):
            break
        idx += 1

    # Résumé final.
    audit_log("planner_end", steps_run=idx, replans=replans)
    if idx >= len(plan):
        return f"Mission accomplie en {len(plan)} étapes, Monsieur."
    return f"J'ai couvert {idx} étape(s) sur {len(plan)}. Dernier état : {results[-1] if results else '—'}."
