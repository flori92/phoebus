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
