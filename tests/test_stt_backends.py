"""Tests de sélection de transcription STT."""

from PHOEBUS.stt_backends import SttCandidate, _choose_candidate, _should_verify


def test_stt_verification_corrige_heure_vers_meteo():
    selected, reason = _choose_candidate([
        SttCandidate("groq", "quelle heure est-il", "heure"),
        SttCandidate("google", "météo de la journée", "meteo"),
    ])

    assert selected.backend == "google"
    assert selected.intent == "meteo"
    assert reason == "verified:google"


def test_stt_verification_garde_primary_si_pas_de_meilleure_intention():
    selected, reason = _choose_candidate([
        SttCandidate("groq", "quelle heure est-il", "heure"),
        SttCandidate("google", "quel air est-il", ""),
    ])

    assert selected.backend == "groq"
    assert selected.intent == "heure"
    assert reason == "primary"


def test_stt_verification_se_declenche_si_primary_vide():
    assert _should_verify("") is True
