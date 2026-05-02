"""Tests du profil runtime CPU/GPU/reseau."""

from PHOEBUS.runtime_resources import (
    Accelerator,
    RuntimeProfile,
    TailscaleStatus,
    choose_placement,
    detect_tailscale,
    task_policy_snapshot,
)


def _profile(*accelerators):
    return RuntimeProfile(
        system="Darwin",
        machine="arm64",
        cpu_brand="Apple M1",
        cpu_count=8,
        memory_total_gb=16.0,
        accelerators=list(accelerators),
        tailscale=TailscaleStatus(installed=False),
    )


def test_stt_prefere_cuda_quand_disponible(monkeypatch):
    monkeypatch.delenv("PHOEBUS_ACCELERATION_MODE", raising=False)
    profile = _profile(Accelerator("CUDA", "cuda", True, "test gpu"))

    decision = choose_placement("stt", profile)

    assert decision.device == "cuda"
    assert decision.backend == "faster-whisper"


def test_taches_systeme_restent_sur_cpu():
    profile = _profile(Accelerator("CUDA", "cuda", True, "test gpu"))

    decision = choose_placement("python_run", profile)

    assert decision.device == "cpu"
    assert decision.backend == "cpu"


def test_policy_snapshot_est_serialisable():
    profile = _profile(Accelerator("Apple Metal/MPS", "mps", True, "torch.mps"))
    snapshot = task_policy_snapshot(profile)

    assert snapshot["vision"]["device"] == "mps"
    assert snapshot["python_run"]["device"] == "cpu"


def test_detect_tailscale_absent(monkeypatch):
    monkeypatch.setattr("PHOEBUS.runtime_resources._find_executable", lambda name: None)

    status = detect_tailscale()

    assert status.installed is False
    assert "introuvable" in status.error
