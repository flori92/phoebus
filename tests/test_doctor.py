"""Tests du doctor PHOEBUS."""

from PHOEBUS.doctor import checks_to_dicts, run_checks


def test_doctor_renvoie_des_checks_serialisables():
    checks = run_checks()
    data = checks_to_dicts(checks)

    assert data
    assert all({"name", "status", "message", "details"} <= set(item) for item in data)
    assert {item["status"] for item in data} <= {"ok", "warn", "fail"}
