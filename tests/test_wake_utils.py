"""Tests des helpers de wake word utilisés par la boucle STT principale."""

from PHOEBUS.wake_utils import has_wake_word, is_stop_conversation, strip_wake_word


def test_detecte_wake_word_dans_bonjour_phoebus():
    assert has_wake_word("Bonjour Phoebus.")


def test_detecte_variantes_stt_frequentes():
    assert has_wake_word("Fibus, donne moi la météo")
    assert has_wake_word("Phobus ouvre YouTube")


def test_nettoie_wake_word_meme_au_milieu():
    assert strip_wake_word("Bonjour Phoebus, donne moi la météo") == "donne moi la météo"


def test_nettoie_wake_word_seul():
    assert strip_wake_word("Phoebus.") == ""


def test_stop_conversation_detecte_merci_phoebus():
    assert is_stop_conversation("Merci Phoebus")
