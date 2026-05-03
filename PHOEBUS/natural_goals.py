"""Resolution de demandes naturelles en actions PHOEBUS.

Ce module sert de filet pragmatique entre les intents exacts et le LLM :
quand Floriace formule un souhait ("je veux...", "trouve-moi...",
"aide-moi a..."), PHOEBUS choisit un outil au lieu de rester sur une
reponse d'incapacite.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Optional


@dataclass(frozen=True)
class GoalResolution:
    name: str
    payload: dict
    reason: str

    @property
    def reply(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


_POLITENESS = (
    "bonjour", "salut", "merci", "ça va", "ca va", "comment vas-tu",
    "qui es-tu", "tu fais quoi",
)
_SEARCH_MARKERS = (
    "cherche", "recherche", "trouve", "trouve-moi", "trouve moi",
    "renseigne", "regarde sur internet", "sur le web", "google",
    "meilleurs", "meilleures", "compare", "comparatif", "avis",
    "recommande", "recommandes", "propose", "proposes",
)
_CURRENT_MARKERS = (
    "aujourd'hui", "maintenant", "actuel", "actuelle", "dernier",
    "dernière", "derniere", "actualité", "actualite", "news", "nouvelles",
    "nouvelle", "bénin", "france", "monde",
    "prix", "disponible", "où trouver", "ou trouver",
)
_QUESTION_MARKERS = (
    "qui", "quoi", "quand", "où", "ou", "comment", "pourquoi",
    "quel", "quelle", "quels", "quelles", "c'est quoi", "explique",
    "définis", "definis", "définition", "definition",
)
_WISH_MARKERS = (
    "je veux", "j'aimerais", "jaimerais", "je voudrais", "aide-moi",
    "aide moi", "il faut", "j'ai besoin", "jai besoin", "fais-moi",
    "fais moi", "peux-tu", "peux tu", "prépare", "prepare",
)
_ACTION_MARKERS = (
    "ouvre", "lance", "mets", "installe", "configure", "crée", "cree",
    "écris", "ecris", "envoie", "organise", "planifie", "réserve",
    "reserve", "achète", "achete", "télécharge", "telecharge",
    "modifie", "corrige", "prépare", "prepare", "nettoie",
)
_LOCAL_TARGET_MARKERS = (
    "sur mon mac", "mon mac", "fichier", "fichiers", "dossier", "dossiers",
    "bureau", "documents", "téléchargements", "telechargements",
    "application", "appli", "logiciel",
)
_INCAPABLE_MARKERS = (
    "je ne peux pas", "je n'ai pas accès", "je n ai pas accès",
    "je n'ai pas acces", "je n ai pas acces", "je ne suis pas capable",
    "je ne peux pas accéder", "je ne peux pas acceder",
    "mes serveurs de réflexion sont temporairement indisponibles",
    "je n'ai pas l'information", "je n ai pas l'information",
    "je ne dispose pas", "je ne peux pas effectuer",
    "erreur lors de l'exécution", "échec", "echec", "raté",
)


def _norm(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t.strip(" ,.!?:;")


def _is_politeness(t: str) -> bool:
    return any(marker in t for marker in _POLITENESS) and len(t.split()) <= 6


def _has_any(t: str, markers: tuple[str, ...]) -> bool:
    return any(marker in t for marker in markers)


def _is_information_need(t: str) -> bool:
    return "?" in t or _has_any(t, _QUESTION_MARKERS)


def _is_search_need(t: str) -> bool:
    return _has_any(t, _SEARCH_MARKERS) or _has_any(t, _CURRENT_MARKERS)


def _is_action_need(t: str) -> bool:
    return _has_any(t, _ACTION_MARKERS)


def resolve_pre_ai_goal(text: str) -> Optional[GoalResolution]:
    """Retourne une action directe pour les demandes naturelles evidentes.

    On reste conservateur : les questions ouvertes vont d'abord au LLM.
    Les recherches explicites et les souhaits d'action sont routés directement.
    """
    t = _norm(text)
    if not t or _is_politeness(t):
        return None

    if _is_search_need(t) and _has_any(t, _LOCAL_TARGET_MARKERS):
        return GoalResolution(
            "agent_planifie",
            {"action": "agent_planifie", "instruction": text.strip()},
            "local_search_or_file_goal",
        )

    if _is_search_need(t):
        return GoalResolution(
            "recherche_web",
            {"action": "recherche_web", "query": text.strip()},
            "explicit_search_or_recommendation",
        )

    if _has_any(t, _WISH_MARKERS) and _is_action_need(t):
        return GoalResolution(
            "agent_planifie",
            {"action": "agent_planifie", "instruction": text.strip()},
            "natural_action_goal",
        )

    return None


def looks_like_incapable_response(response: str) -> bool:
    t = _norm(response)
    return bool(t and _has_any(t, _INCAPABLE_MARKERS))


def resolve_after_ai_failure(text: str, response: str = "") -> Optional[GoalResolution]:
    """Filet apres echec/absence/incapacite IA."""
    t = _norm(text)
    if not t or _is_politeness(t):
        return None

    if response and not looks_like_incapable_response(response):
        return None

    if _is_search_need(t) or _is_information_need(t):
        action = "recherche_web" if _has_any(t, _CURRENT_MARKERS + _SEARCH_MARKERS) else "knowledge_query"
        key = "query" if action == "recherche_web" else "question"
        return GoalResolution(action, {"action": action, key: text.strip()}, "ai_fallback_information")

    if _has_any(t, _WISH_MARKERS) or _is_action_need(t):
        return GoalResolution(
            "agent_planifie",
            {"action": "agent_planifie", "instruction": text.strip()},
            "ai_fallback_action",
        )

    return GoalResolution(
        "recherche_web",
        {"action": "recherche_web", "query": text.strip()},
        "ai_fallback_default_search",
    )
