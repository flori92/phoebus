"""Detection runtime et politique de placement CPU/GPU/reseau.

PHOEBUS doit savoir ce que la machine peut executer localement avant de router
une tache. Ce module reste sans dependance dure: Torch, CTranslate2, Tailscale
ou psutil sont detectes si presents, sinon le profil retombe proprement sur CPU.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

_PROFILE_CACHE: dict[str, Any] = {"ts": 0.0, "profile": None}


@dataclass(frozen=True, slots=True)
class Accelerator:
    name: str
    kind: str
    available: bool
    details: str = ""


@dataclass(frozen=True, slots=True)
class TailscaleStatus:
    installed: bool
    up: bool = False
    ip4: str = ""
    hostname: str = ""
    tailnet: str = ""
    peers: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    system: str
    machine: str
    cpu_brand: str
    cpu_count: int
    memory_total_gb: float | None
    accelerators: list[Accelerator]
    tailscale: TailscaleStatus

    @property
    def has_cuda(self) -> bool:
        return any(acc.available and acc.kind == "cuda" for acc in self.accelerators)

    @property
    def has_mps(self) -> bool:
        return any(acc.available and acc.kind == "mps" for acc in self.accelerators)

    @property
    def has_gpu(self) -> bool:
        return any(
            acc.available and acc.kind in {"cuda", "mps", "metal"} for acc in self.accelerators
        )


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    task: str
    device: str
    backend: str
    reason: str
    compute_type: str = ""


def _env_choice(name: str, default: str = "auto") -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _run_json(cmd: list[str], timeout: float = 2.0) -> dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def _run_json_with_error(cmd: list[str], timeout: float = 2.0) -> tuple[dict, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {}, (result.stderr or result.stdout or "").strip()
        return json.loads(result.stdout or "{}"), ""
    except Exception as exc:
        return {}, str(exc)


def _run_text(cmd: list[str], timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _find_executable(name: str) -> str | None:
    exe = shutil.which(name)
    if exe:
        return exe
    for path in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    return None


def _cpu_brand() -> str:
    if platform.system() == "Darwin":
        brand = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=1.0)
        if brand:
            return brand
    return platform.processor() or platform.machine()


def _memory_total_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return None


def _torch_accelerators() -> list[Accelerator]:
    accelerators: list[Accelerator] = []
    try:
        import torch

        cuda_ok = bool(torch.cuda.is_available())
        accelerators.append(
            Accelerator(
                name="CUDA",
                kind="cuda",
                available=cuda_ok,
                details=torch.cuda.get_device_name(0) if cuda_ok else "",
            )
        )
        mps_backend = getattr(torch.backends, "mps", None)
        mps_ok = bool(mps_backend and mps_backend.is_available())
        accelerators.append(
            Accelerator(
                name="Apple Metal/MPS",
                kind="mps",
                available=mps_ok,
                details="torch.mps" if mps_ok else "",
            )
        )
    except Exception as exc:
        accelerators.append(Accelerator("Torch", "torch", False, f"{type(exc).__name__}: {exc}"))
    return accelerators


def _ctranslate2_accelerator() -> Accelerator:
    try:
        import ctranslate2

        try:
            cuda_types = ctranslate2.get_supported_compute_types("cuda")
        except Exception:
            cuda_types = set()
        cpu_types = ctranslate2.get_supported_compute_types("cpu")
        if cuda_types:
            return Accelerator("CTranslate2 CUDA", "cuda", True, ",".join(sorted(cuda_types)))
        return Accelerator("CTranslate2 CPU", "cpu", True, ",".join(sorted(cpu_types)))
    except Exception as exc:
        return Accelerator("CTranslate2", "cpu", False, f"{type(exc).__name__}: {exc}")


def _apple_metal_accelerator() -> Accelerator:
    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    if not is_apple_silicon:
        return Accelerator("Apple Metal", "metal", False, "")
    return Accelerator("Apple Metal", "metal", True, _cpu_brand())


def detect_tailscale() -> TailscaleStatus:
    exe = _find_executable("tailscale")
    if not exe:
        return TailscaleStatus(installed=False, error="tailscale CLI introuvable")

    data, status_error = _run_json_with_error([exe, "status", "--json"], timeout=2.0)
    ip4 = _run_text([exe, "ip", "-4"], timeout=1.5)
    if not data:
        return TailscaleStatus(
            installed=True,
            ip4=ip4,
            error=status_error or "status indisponible",
        )

    self_info = data.get("Self") or {}
    peers = data.get("Peer") or {}
    backend_state = str(data.get("BackendState") or "").lower()
    return TailscaleStatus(
        installed=True,
        up=backend_state == "running" or bool(ip4),
        ip4=ip4.splitlines()[0] if ip4 else "",
        hostname=str(self_info.get("HostName") or self_info.get("DNSName") or ""),
        tailnet=str(data.get("MagicDNSSuffix") or ""),
        peers=len(peers) if isinstance(peers, dict) else 0,
    )


def detect_profile(force: bool = False) -> RuntimeProfile:
    now = time.time()
    ttl = float(os.getenv("PHOEBUS_RUNTIME_PROFILE_TTL", "30"))
    cached = _PROFILE_CACHE.get("profile")
    if cached is not None and not force and now - float(_PROFILE_CACHE["ts"]) < ttl:
        return cached

    accelerators = _torch_accelerators()
    accelerators.append(_ctranslate2_accelerator())
    accelerators.append(_apple_metal_accelerator())
    profile = RuntimeProfile(
        system=platform.system(),
        machine=platform.machine(),
        cpu_brand=_cpu_brand(),
        cpu_count=os.cpu_count() or 1,
        memory_total_gb=_memory_total_gb(),
        accelerators=accelerators,
        tailscale=detect_tailscale(),
    )
    _PROFILE_CACHE.update({"ts": now, "profile": profile})
    return profile


def choose_placement(task: str, profile: RuntimeProfile | None = None) -> PlacementDecision:
    """Retourne ou executer une famille de tache.

    `PHOEBUS_ACCELERATION_MODE=cpu` force le CPU. En `auto`, les taches
    temps-reel courtes restent CPU/IO, les charges neurales longues prennent
    CUDA/MPS quand disponible.
    """
    task = (task or "general").strip().lower()
    mode = _env_choice("PHOEBUS_ACCELERATION_MODE", "auto")
    profile = profile or detect_profile()

    if mode == "cpu":
        return PlacementDecision(task, "cpu", "cpu", "mode cpu force")

    if task in {"system", "python_run", "scheduler", "network", "tailscale", "io"}:
        return PlacementDecision(task, "cpu", "cpu", "tache systeme ou IO")

    if task in {"stt", "whisper", "voice"}:
        stt_device = _env_choice("PHOEBUS_WHISPER_DEVICE", "auto")
        compute_type = os.getenv("PHOEBUS_WHISPER_COMPUTE_TYPE", "auto").strip() or "auto"
        if profile.has_cuda and stt_device in {"auto", "cuda", "gpu"}:
            return PlacementDecision(
                task, "cuda", "faster-whisper", "CUDA disponible", compute_type
            )
        if profile.has_mps and _module_available("mlx_whisper"):
            return PlacementDecision(task, "mps", "mlx-whisper", "Apple MPS + MLX disponibles")
        if profile.has_mps:
            return PlacementDecision(
                task,
                "auto",
                "faster-whisper",
                "Apple GPU detecte; faster-whisper garde son device auto",
                compute_type,
            )
        return PlacementDecision(task, "cpu", "faster-whisper", "fallback CPU", compute_type)

    if task in {"vision", "embedding", "local_llm", "generation"}:
        if profile.has_cuda:
            return PlacementDecision(task, "cuda", "torch", "charge neurale lourde")
        if profile.has_mps:
            return PlacementDecision(task, "mps", "torch", "charge neurale lourde Apple Silicon")
        return PlacementDecision(task, "cpu", "cpu", "aucun GPU detecte")

    return PlacementDecision(task, "cpu", "cpu", "placement par defaut")


def _module_available(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def task_policy_snapshot(profile: RuntimeProfile | None = None) -> dict[str, dict]:
    profile = profile or detect_profile()
    tasks = ("stt", "vision", "local_llm", "python_run", "network", "scheduler")
    return {task: asdict(choose_placement(task, profile)) for task in tasks}


def runtime_snapshot(force: bool = False) -> dict:
    profile = detect_profile(force=force)
    return {
        "profile": asdict(profile),
        "task_policy": task_policy_snapshot(profile),
    }
