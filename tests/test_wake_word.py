"""Tests pour la sélection du backend wake word."""

import PHOEBUS.wake_word as wake_word


def test_auto_prefere_backend_phoebus_avant_oww(monkeypatch):
    calls = []

    monkeypatch.delenv("PHOEBUS_WAKE_BACKEND", raising=False)
    monkeypatch.setattr(wake_word, "_try_oww", lambda: calls.append("oww") or True)
    monkeypatch.setattr(wake_word, "_try_vosk", lambda: calls.append("vosk") or True)
    monkeypatch.setattr(wake_word, "_try_pocketsphinx", lambda: calls.append("pocketsphinx") or True)
    monkeypatch.setattr(wake_word, "_run_fallback_stt", lambda: calls.append("stt"))

    wake_word._run()

    assert calls == ["vosk"]


def test_auto_bascule_sur_stt_si_backends_locaux_indisponibles(monkeypatch):
    calls = []

    monkeypatch.setenv("PHOEBUS_WAKE_BACKEND", "auto")
    monkeypatch.setattr(wake_word, "_try_oww", lambda: calls.append("oww") or True)
    monkeypatch.setattr(wake_word, "_try_vosk", lambda: calls.append("vosk") or False)
    monkeypatch.setattr(wake_word, "_try_pocketsphinx", lambda: calls.append("pocketsphinx") or False)
    monkeypatch.setattr(wake_word, "_run_fallback_stt", lambda: calls.append("stt"))

    wake_word._run()

    assert calls == ["vosk", "pocketsphinx", "stt"]


def test_oww_reste_disponible_si_force(monkeypatch):
    calls = []

    monkeypatch.setenv("PHOEBUS_WAKE_BACKEND", "oww")
    monkeypatch.setattr(wake_word, "_try_oww", lambda: calls.append("oww") or True)
    monkeypatch.setattr(wake_word, "_try_vosk", lambda: calls.append("vosk") or True)
    monkeypatch.setattr(wake_word, "_try_pocketsphinx", lambda: calls.append("pocketsphinx") or True)
    monkeypatch.setattr(wake_word, "_run_fallback_stt", lambda: calls.append("stt"))

    wake_word._run()

    assert calls == ["oww"]
