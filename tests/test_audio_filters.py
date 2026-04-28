"""Tests des filtres de bruit audio/STT."""

from PHOEBUS.audio_optimization import check_hallucination
from PHOEBUS.clarify import transcription_bruit_media


def test_bruit_media_ignore_outro_youtube():
    assert transcription_bruit_media("Merci d'avoir regardé cette vidéo !")


def test_bruit_media_ignore_sous_titrage_st():
    assert transcription_bruit_media("Sous-titrage ST' 501")


def test_bruit_media_ignore_sous_titres_auteur():
    assert transcription_bruit_media("Sous-titres par Jérémy Diaz")


def test_bruit_media_ne_bloque_pas_wake_word():
    assert not transcription_bruit_media("PHOEBUS météo de la journée")


def test_check_hallucination_utilise_filtre_media():
    is_hallucination, confidence = check_hallucination("Sous-titrage ST' 501")

    assert is_hallucination is True
    assert confidence == 0.0
