"""Tests d'intentions locales."""

import json

from PHOEBUS.intent import detect


def _payload(texte: str) -> dict:
    intent = detect(texte)
    assert intent is not None
    return json.loads(intent.reply)


def test_meteo_journee_sans_ville():
    payload = _payload("météo de la journée")

    assert payload == {"action": "meteo", "periode": "journee"}


def test_meteo_aujourd_hui_sans_fausse_ville():
    payload = _payload("quel temps fait-il aujourd hui")

    assert payload == {"action": "meteo", "periode": "journee"}


def test_meteo_du_jour_sans_fausse_ville():
    payload = _payload("météo du jour")

    assert payload == {"action": "meteo", "periode": "journee"}


def test_meteo_ville_extrait_la_vraie_ville():
    payload = _payload("quel temps fait-il à Amilly")

    assert payload == {"action": "meteo", "ville": "amilly"}


def test_media_film_comique_declenche_recommandations_vod():
    payload = _payload("je veux regarder un film comique")

    assert payload == {
        "action": "media_recommendations",
        "kind": "film",
        "genre": "comedie",
        "platform": "justwatch",
        "open": True,
    }


def test_media_netflix_garde_plateforme_demandee():
    payload = _payload("trouve-moi une série thriller sur Netflix")

    assert payload["action"] == "media_recommendations"
    assert payload["kind"] == "serie"
    assert payload["genre"] == "thriller"
    assert payload["platform"] == "netflix"


def test_email_gmail_route_vers_write_email():
    payload = _payload(
        "Phoebus, prépare un message test pour florifavi@gmail.com "
        "avec le sujet Test Phoebus et le texte Ceci est un test"
    )

    assert payload == {
        "action": "write_email",
        "recipient": "florifavi@gmail.com",
        "subject": "test phoebus",
        "body": "ceci est un test",
    }
