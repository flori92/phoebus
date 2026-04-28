"""Tests du garde-fou anti-boucle d'actions."""

from PHOEBUS.action_guard import ActionGuardConfig, ActionSequenceGuard


def test_action_guard_bloque_action_identique_repetee():
    guard = ActionSequenceGuard(ActionGuardConfig(max_identical_calls=2))
    payload = {"action": "ha_lumiere", "piece": "salon", "etat": "on"}

    assert guard.check(payload).blocked is False
    assert guard.check(payload).blocked is False
    verdict = guard.check(payload)

    assert verdict.blocked is True
    assert "répétée" in verdict.reason


def test_action_guard_bloque_trop_actions():
    guard = ActionSequenceGuard(ActionGuardConfig(max_actions_per_batch=2))

    assert guard.check({"action": "a"}).blocked is False
    assert guard.check({"action": "b"}).blocked is False
    verdict = guard.check({"action": "c"})

    assert verdict.blocked is True
    assert "trop d'actions" in verdict.reason


def test_action_guard_detecte_ping_pong():
    guard = ActionSequenceGuard(
        ActionGuardConfig(
            max_identical_calls=10,
            max_actions_per_batch=10,
            ping_pong_window=4,
        )
    )

    assert guard.check({"action": "a", "n": 1}).blocked is False
    assert guard.check({"action": "b", "n": 1}).blocked is False
    assert guard.check({"action": "a", "n": 1}).blocked is False
    verdict = guard.check({"action": "b", "n": 1})

    assert verdict.blocked is True
    assert "cycle" in verdict.reason
