"""Tests du routage de demandes naturelles."""

from PHOEBUS.natural_goals import (
    looks_like_incapable_response,
    resolve_after_ai_failure,
    resolve_pre_ai_goal,
)


def test_pre_ai_goal_recherche_explicite():
    goal = resolve_pre_ai_goal("trouve-moi les meilleurs casques bluetooth")

    assert goal is not None
    assert goal.name == "recherche_web"
    assert goal.payload["query"] == "trouve-moi les meilleurs casques bluetooth"


def test_pre_ai_goal_action_naturelle_va_au_planificateur():
    goal = resolve_pre_ai_goal("je veux installer VLC sur mon Mac")

    assert goal is not None
    assert goal.name == "agent_planifie"
    assert goal.payload["instruction"] == "je veux installer VLC sur mon Mac"


def test_recherche_locale_va_au_planificateur_pas_au_web():
    goal = resolve_pre_ai_goal("trouve-moi le fichier facture sur mon Mac")

    assert goal is not None
    assert goal.name == "agent_planifie"


def test_question_simple_n_est_pas_preemptee_avant_ia():
    assert resolve_pre_ai_goal("explique moi la virtualisation") is None


def test_incapable_response_declenche_fallback_knowledge():
    goal = resolve_after_ai_failure(
        "explique moi la virtualisation",
        "Je ne peux pas accéder à cette information.",
    )

    assert goal is not None
    assert goal.name == "knowledge_query"
    assert goal.payload["question"] == "explique moi la virtualisation"


def test_detecte_reponse_incapable():
    assert looks_like_incapable_response("Je ne peux pas accéder à ça.")
