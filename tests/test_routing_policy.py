"""Tests du routeur déterministe."""

from PHOEBUS.routing_policy import decide_route


def test_route_simple_intent_heure():
    decision = decide_route("quelle heure est-il")

    assert decision.route == "simple"
    assert decision.reply
    assert decision.confidence > 0.9


def test_route_intent_meteo_est_recherche():
    decision = decide_route("quelle est la météo de la journée")

    assert decision.route == "search"
    assert decision.payload == {"action": "meteo", "periode": "journee"}


def test_route_recherche_web():
    decision = decide_route("trouve-moi les meilleurs casques bluetooth")

    assert decision.route == "search"
    assert decision.payload == {
        "action": "recherche_web",
        "query": "trouve-moi les meilleurs casques bluetooth",
    }


def test_route_agent_local():
    decision = decide_route("cherche le fichier facture sur mon Mac")

    assert decision.route == "agent"
    assert decision.payload == {
        "action": "agent_planifie",
        "instruction": "cherche le fichier facture sur mon Mac",
    }
