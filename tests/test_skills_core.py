"""Tests des capacités noyau exposées à PHOEBUS."""

import pytest

from PHOEBUS.skills import IMPORT_ERRORS, capability_manifest, execute_skill, list_skills


def test_capability_manifest_reflète_les_skills_noyau():
    manifest = capability_manifest()
    skills = set(list_skills())

    assert "python_run" in skills
    assert "brain_status" in skills
    assert "CAPACITES ENREGISTREES" in manifest
    assert "- python_run" in manifest
    assert "- brain_status" in manifest
    assert isinstance(IMPORT_ERRORS, dict)


@pytest.mark.asyncio
async def test_python_run_execute_calcul_contraint():
    ok, msg = await execute_skill("python_run", {"code": "print(6 * 7)"})

    assert ok is True
    assert msg.strip() == "42"


@pytest.mark.asyncio
async def test_brain_status_retourne_un_resume_sans_reseau():
    ok, msg = await execute_skill("brain_status", {})

    assert ok is True
    assert "Mode cerveau:" in msg
    assert "Providers:" in msg
