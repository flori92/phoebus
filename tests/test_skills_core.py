"""Tests des capacités noyau exposées à PHOEBUS."""

import pytest

from PHOEBUS.skills import IMPORT_ERRORS, capability_manifest, execute_skill, list_skills


def test_capability_manifest_reflète_les_skills_noyau():
    manifest = capability_manifest()
    skills = set(list_skills())

    assert "python_run" in skills
    assert "brain_status" in skills
    assert "runtime_status" in skills
    assert "tailscale_status" in skills
    assert "task_status" in skills
    assert "cache_status" in skills
    assert "phone_control" in skills
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


@pytest.mark.asyncio
async def test_runtime_et_cache_status_repondent():
    ok_runtime, runtime_msg = await execute_skill("runtime_status", {})
    ok_cache, cache_msg = await execute_skill("cache_status", {})

    assert ok_runtime is True
    assert "Runtime:" in runtime_msg
    assert ok_cache is True
    assert "Cache vocal:" in cache_msg
