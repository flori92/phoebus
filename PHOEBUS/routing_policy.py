# PHOEBUS/routing_policy.py
"""Routage déterministe des requêtes utilisateur.

Le LLM ne doit pas être le premier réflexe pour tout. Ce module classe une
phrase en `simple`, `search`, `agent`, `action` ou `chat` sans appel réseau.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from PHOEBUS.intent import detect as detect_intent
from PHOEBUS.natural_goals import resolve_pre_ai_goal


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str
    confidence: float
    reply: str = ""
    payload: dict[str, Any] | None = None
    intent_name: str = ""
    local_first: bool = True

    @property
    def needs_ai(self) -> bool:
        return self.route == "chat"


_SEARCH_ACTIONS = {"recherche_web", "knowledge_query", "meteo", "alerte_meteo"}
_AGENT_ACTIONS = {"agent_planifie"}

_SEARCH_MARKERS = (
    "cherche",
    "recherche",
    "trouve",
    "trouve-moi",
    "trouve moi",
    "compare",
    "comparatif",
    "actualité",
    "actualite",
    "dernier",
    "dernière",
    "derniere",
    "aujourd'hui",
    "maintenant",
    "prix",
    "avis",
    "recommande",
)

_AGENT_MARKERS = (
    "installe",
    "configure",
    "prépare",
    "prepare",
    "organise",
    "planifie",
    "corrige",
    "crée",
    "cree",
    "modifie",
    "nettoie",
    "télécharge",
    "telecharge",
)

_LOCAL_TARGET_MARKERS = (
    "sur mon mac",
    "mon mac",
    "fichier",
    "fichiers",
    "dossier",
    "application",
    "logiciel",
)


def decide_route(text: str, source: str = "voice") -> RouteDecision:
    """Classe une requête sans appel réseau."""
    raw = (text or "").strip()
    t = raw.lower()
    if not raw:
        return RouteDecision("chat", "empty", 0.0)

    intent = detect_intent(raw)
    if intent is not None:
        payload = _json_payload(intent.reply)
        if payload is not None:
            action = str(payload.get("action") or "")
            if action in _AGENT_ACTIONS:
                route = "agent"
            elif action in _SEARCH_ACTIONS:
                route = "search"
            else:
                route = "action"
            return RouteDecision(
                route=route,
                reason=f"intent:{intent.name}",
                confidence=intent.confidence,
                reply=intent.reply,
                payload=payload,
                intent_name=intent.name,
            )
        return RouteDecision(
            route="simple",
            reason=f"intent:{intent.name}",
            confidence=intent.confidence,
            reply=intent.reply,
            intent_name=intent.name,
        )

    goal = resolve_pre_ai_goal(raw)
    if goal is not None:
        action = str(goal.payload.get("action") or "")
        if action in _AGENT_ACTIONS:
            route = "agent"
        elif action in _SEARCH_ACTIONS:
            route = "search"
        else:
            route = "action"
        return RouteDecision(
            route=route,
            reason=goal.reason,
            confidence=0.9,
            reply=goal.reply,
            payload=goal.payload,
        )

    if _has_any(t, _SEARCH_MARKERS):
        if _has_any(t, _LOCAL_TARGET_MARKERS):
            payload = {"action": "agent_planifie", "instruction": raw}
            return RouteDecision("agent", "deterministic_local_search", 0.82, payload=payload)
        payload = {"action": "recherche_web", "query": raw}
        return RouteDecision("search", "deterministic_search", 0.82, payload=payload)

    if _has_any(t, _AGENT_MARKERS):
        return RouteDecision(
            "agent",
            "deterministic_action_goal",
            0.78,
            payload={"action": "agent_planifie", "instruction": raw},
        )

    return RouteDecision("chat", "open_conversation", 0.55)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _json_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
