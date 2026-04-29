"""Tests du pairing WebSocket local."""

import PHOEBUS.ws_pairing as pairing


def test_pairing_enroll_validate_and_redact(tmp_path, monkeypatch):
    monkeypatch.setattr(pairing, "PAIRINGS_FILE", tmp_path / "pairs.json")
    monkeypatch.setattr(pairing, "PAIRING_ENABLED", True)
    monkeypatch.setattr(pairing, "AUTO_ENROLL_LOCAL", True)

    enrolled = pairing.enroll_pairing(
        client_ip="127.0.0.1",
        client_type="web",
        client_name="pytest",
    )

    assert enrolled is not None
    assert pairing.validate_pairing(enrolled["device_id"], enrolled["secret"]) is True
    assert pairing.validate_pairing(enrolled["device_id"], "wrong") is False
    data = pairing._load()
    assert data["devices"][enrolled["device_id"]]["secret_hash"] != enrolled["secret"]


def test_pairing_refuse_non_local_auto_enroll(tmp_path, monkeypatch):
    monkeypatch.setattr(pairing, "PAIRINGS_FILE", tmp_path / "pairs.json")
    monkeypatch.setattr(pairing, "PAIRING_ENABLED", True)
    monkeypatch.setattr(pairing, "AUTO_ENROLL_LOCAL", True)

    enrolled = pairing.enroll_pairing(
        client_ip="8.8.8.8",
        client_type="web",
        client_name="pytest",
    )

    assert enrolled is None
