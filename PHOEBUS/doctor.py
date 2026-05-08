# PHOEBUS/doctor.py
"""Diagnostic structuré de PHOEBUS.

OpenJarvis expose un `doctor` qui vérifie l'environnement avant de chercher des
bugs applicatifs. PHOEBUS reprend ce principe avec des checks adaptés au mode
voix/local : runtime unique, dépendances audio, STT, frontend, tokens et ports.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    message: str
    details: str = ""


def _ok(name: str, message: str, details: str = "") -> CheckResult:
    return CheckResult(name, "ok", message, details)


def _warn(name: str, message: str, details: str = "") -> CheckResult:
    return CheckResult(name, "warn", message, details)


def _fail(name: str, message: str, details: str = "") -> CheckResult:
    return CheckResult(name, "fail", message, details)


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _run(cmd: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _find_executable(name: str) -> str | None:
    exe = shutil.which(name) or shutil.which(f"{name}.cmd")
    if exe:
        return exe

    candidates = [
        os.path.expanduser(f"~/.nvm/versions/node/*/bin/{name}"),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ]
    for pattern in candidates:
        for path in sorted(glob.glob(pattern), reverse=True):
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path

    try:
        out = subprocess.check_output(
            ["/bin/zsh", "-lc", f"command -v {name}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return None


def _check_python() -> CheckResult:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        return _ok("Python", version)
    return _fail("Python", f"{version} non supporté", "PHOEBUS requiert Python 3.11+.")


def _check_imports() -> list[CheckResult]:
    required = {
        "dotenv": "configuration .env",
        "requests": "HTTP",
        "speech_recognition": "STT",
        "websockets": "interface WebSocket",
        "pygame": "lecture audio",
        "openai": "clients OpenAI-compatibles",
    }
    optional = {
        "pyaudio": "micro local",
        "webrtcvad": "VAD audio",
        "chromadb": "mémoire RAG",
    }
    checks: list[CheckResult] = []
    for module, label in required.items():
        checks.append(
            _ok(f"Module {module}", label)
            if _has_module(module)
            else _fail(f"Module {module}", "manquant", label)
        )
    for module, label in optional.items():
        checks.append(
            _ok(f"Option {module}", label)
            if _has_module(module)
            else _warn(f"Option {module}", "non installé", label)
        )
    return checks


def _check_config() -> list[CheckResult]:
    try:
        from PHOEBUS.config import (
            DEFAULT_MOBILE_PORT,
            DEFAULT_WS_PORT,
            GEMINI_API_KEY,
            GROQ_API_KEY,
            MISTRAL_API_KEY,
            OPENAI_API_KEY,
            SERPAPI_API_KEY,
            TELEGRAM_TOKEN,
            WS_AUTH_REQUIRED,
            XAI_API_KEY,
            _secret_is_configured,
        )
    except Exception as exc:
        return [_fail("Configuration", f"import impossible: {exc}")]

    checks = [
        _ok("Port WebSocket", str(DEFAULT_WS_PORT)),
        _ok("Port mobile", str(DEFAULT_MOBILE_PORT)),
        (
            _ok("Auth WebSocket", "active")
            if WS_AUTH_REQUIRED
            else _warn("Auth WebSocket", "désactivée")
        ),
    ]

    providers = []
    if _secret_is_configured(GEMINI_API_KEY):
        providers.append("gemini")
    if _secret_is_configured(GROQ_API_KEY):
        providers.append("groq")
    if _secret_is_configured(XAI_API_KEY):
        providers.append("grok")
    if _secret_is_configured(MISTRAL_API_KEY):
        providers.append("mistral")
    if _secret_is_configured(OPENAI_API_KEY):
        providers.append("openai")
    if _secret_is_configured(SERPAPI_API_KEY):
        providers.append("serpapi")
    if _secret_is_configured(TELEGRAM_TOKEN):
        providers.append("telegram")
    checks.append(
        _ok("Services configurés", ", ".join(providers))
        if providers
        else _warn("Services configurés", "aucun service cloud détecté")
    )
    return checks


def _check_ollama_local() -> CheckResult:
    try:
        from PHOEBUS.config import OLLAMA_MODELS, OLLAMA_URL
        import urllib.request

        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return _warn("Ollama local", f"non joignable: {exc}")

    installed = {
        item.get("name") or item.get("model")
        for item in data.get("models", [])
        if isinstance(item, dict)
    }
    wanted = OLLAMA_MODELS[0] if OLLAMA_MODELS else ""
    if wanted and wanted in installed:
        return _ok("Ollama local", f"{wanted} installé")
    if wanted:
        return _warn(
            "Ollama local",
            f"{wanted} absent",
            "installez-le avec: ollama pull " + wanted,
        )
    return _warn("Ollama local", "aucun modèle configuré")


def _check_stt() -> CheckResult:
    try:
        from PHOEBUS.stt_backends import stt_status

        status = stt_status()
    except Exception as exc:
        return _fail("STT", f"erreur: {exc}")
    available = status.get("available") or {}
    order = status.get("auto_order") or []
    first_available = next((name for name in order if available.get(name)), None)
    if not first_available and not any(available.values()):
        return _fail("STT", "aucun backend disponible")
    placement = status.get("placement") or {}
    backend = status.get("requested")
    active = backend if backend != "auto" else first_available
    return _ok(
        "STT",
        f"{active} ({placement.get('device', 'cpu')}/{placement.get('backend', 'auto')})",
        f"ordre={','.join(order)} modèle={status.get('whisper_model')}",
    )


def _check_runtime_resources() -> list[CheckResult]:
    try:
        from PHOEBUS.runtime_resources import runtime_snapshot

        snap = runtime_snapshot()
    except Exception as exc:
        return [_warn("Runtime ressources", f"indisponible: {exc}")]

    profile = snap.get("profile") or {}
    accelerators = [
        item
        for item in profile.get("accelerators", [])
        if isinstance(item, dict) and item.get("available")
    ]
    checks = [
        _ok(
            "Placement tâches",
            f"CPU {profile.get('cpu_count')} coeur(s)",
            f"policy={json.dumps(snap.get('task_policy', {}), ensure_ascii=False)[:300]}",
        )
    ]
    if accelerators:
        details = ", ".join(f"{a.get('name')}:{a.get('kind')}" for a in accelerators)
        checks.append(_ok("Accélération locale", "disponible", details))
    else:
        checks.append(_warn("Accélération locale", "aucun GPU utilisable détecté"))

    ts = profile.get("tailscale") or {}
    if not ts.get("installed"):
        checks.append(
            _warn("Tailscale", "non installé", "brew install tailscale puis tailscale up")
        )
    elif ts.get("up"):
        checks.append(_ok("Tailscale", ts.get("ip4") or "connecté", f"pairs={ts.get('peers')}"))
    else:
        checks.append(_warn("Tailscale", "installé mais non connecté", ts.get("error", "")))
    return checks


def _check_runtime_singleton() -> CheckResult:
    try:
        result = _run(["pgrep", "-f", "[m]ain2.py --auto-restart"])
    except Exception as exc:
        return _warn("Runtime unique", f"non vérifié: {exc}")
    pids = []
    for pid in (p for p in result.stdout.splitlines() if p.strip()):
        try:
            ps = _run(["ps", "-p", pid, "-o", "command="])
            command = ps.stdout.strip()
        except Exception:
            command = ""
        lower = command.lower()
        is_launcher_shell = lower.startswith(("/bin/zsh", "/bin/sh", "/bin/bash"))
        if "main2.py --auto-restart" in lower and not is_launcher_shell:
            pids.append(pid)
    if len(pids) <= 1:
        return _ok("Runtime unique", f"{len(pids)} instance")
    return _fail("Runtime unique", f"{len(pids)} instances", "PID: " + ", ".join(pids))


def _check_frontend() -> list[CheckResult]:
    checks: list[CheckResult] = []
    npm = _find_executable("npm")
    if not npm:
        return [_warn("Frontend npm", "npm introuvable")]
    checks.append(_ok("Frontend npm", npm))
    package_json = ROOT / "frontend" / "package.json"
    checks.append(
        _ok("Frontend package", "présent")
        if package_json.exists()
        else _warn("Frontend package", "absent")
    )
    return checks


def _check_health_endpoint() -> CheckResult:
    try:
        from PHOEBUS.config import DEFAULT_MOBILE_PORT
        import urllib.request

        with urllib.request.urlopen(
            f"http://127.0.0.1:{DEFAULT_MOBILE_PORT}/health",
            timeout=1.5,
        ) as response:
            if response.status == 200:
                return _ok("Endpoint /health", "répond")
            return _warn("Endpoint /health", f"HTTP {response.status}")
    except Exception:
        return _warn("Endpoint /health", "non joignable", "normal si PHOEBUS n'est pas lancé")


def _check_request_metrics() -> CheckResult:
    try:
        from PHOEBUS.observability import request_snapshot

        snap = request_snapshot(limit=200, max_age_seconds=24 * 3600)
    except Exception as exc:
        return _warn("Métriques requêtes", f"indisponibles: {exc}")
    if not snap.get("count"):
        return _warn("Métriques requêtes", "aucune requête enregistrée")
    last = snap.get("last") or {}
    return _ok(
        "Métriques requêtes",
        f"24h p50={snap['p50_ms']}ms p95={snap['p95_ms']}ms",
        f"dernière={last.get('duration_ms')}ms source={last.get('source')}",
    )


def _check_agent_traces() -> CheckResult:
    try:
        from PHOEBUS.agent_runtime import recent_agent_runs

        runs = recent_agent_runs(limit=1)
    except Exception as exc:
        return _warn("Traces agent", f"indisponibles: {exc}")
    if not runs:
        return _warn("Traces agent", "aucune trace agent")
    run = runs[-1]
    return _ok(
        "Traces agent",
        f"dernier run {run.get('status')}",
        f"{len(run.get('steps') or [])} étape(s), {run.get('duration_ms')}ms",
    )


def _check_memory_backend() -> CheckResult:
    try:
        from PHOEBUS.rag_memory import rag_status

        status = rag_status()
    except Exception as exc:
        return _warn("Mémoire retrieval", f"indisponible: {exc}")
    fallback = status.get("sqlite_fallback") or {}
    if fallback.get("available"):
        chroma = "prêt" if status.get("chroma_ready") else "fallback actif"
        return _ok(
            "Mémoire retrieval",
            chroma,
            f"sqlite={fallback.get('count', 0)} souvenirs",
        )
    return _fail("Mémoire retrieval", "SQLite fallback indisponible")


def _check_tts_cache() -> CheckResult:
    try:
        from PHOEBUS.response_cache import status

        snap = status()
    except Exception as exc:
        return _warn("Cache vocal", f"indisponible: {exc}")
    return _ok(
        "Cache vocal",
        f"{snap.get('entries', 0)} entrée(s), {snap.get('size_mb', 0)} Mo",
        str(snap.get("dir", "")),
    )


def _check_core_skills() -> CheckResult:
    expected = {
        "agent_planifie",
        "brain_status",
        "cache_status",
        "knowledge_query",
        "meteo",
        "python_run",
        "recherche_web",
        "runtime_status",
        "tailscale_status",
        "task_status",
    }
    try:
        from PHOEBUS.skills import IMPORT_ERRORS, capability_manifest, list_skills

        skills = set(list_skills())
        manifest = capability_manifest()
    except Exception as exc:
        return _fail("Skills noyau", f"registre indisponible: {exc}")

    missing = sorted(expected - skills)
    if missing:
        return _fail("Skills noyau", "actions manquantes", ", ".join(missing))
    if not manifest:
        return _warn("Skills noyau", "manifeste vide")
    if IMPORT_ERRORS:
        details = "; ".join(f"{name}: {err}" for name, err in IMPORT_ERRORS.items())
        return _warn("Skills noyau", f"{len(skills)} skills, imports partiels", details[:500])
    return _ok("Skills noyau", f"{len(skills)} skills enregistrés")


def run_checks() -> list[CheckResult]:
    checks = [_check_python()]
    checks.extend(_check_imports())
    checks.extend(_check_config())
    checks.append(_check_core_skills())
    checks.extend(_check_runtime_resources())
    checks.append(_check_ollama_local())
    checks.append(_check_stt())
    checks.append(_check_runtime_singleton())
    checks.extend(_check_frontend())
    checks.append(_check_health_endpoint())
    checks.append(_check_request_metrics())
    checks.append(_check_agent_traces())
    checks.append(_check_memory_backend())
    checks.append(_check_tts_cache())
    return checks


def checks_to_dicts(checks: list[CheckResult]) -> list[dict]:
    return [asdict(check) for check in checks]


def print_report(checks: list[CheckResult]) -> None:
    icons = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    print("PHOEBUS Doctor")
    print(f"Racine : {ROOT}")
    print(f"Système: {platform.system()} {platform.release()} ({platform.machine()})")
    print()
    for check in checks:
        detail = f" - {check.details}" if check.details else ""
        print(
            f"[{icons.get(check.status, check.status.upper()):4}] "
            f"{check.name}: {check.message}{detail}"
        )
    print()
    ok = sum(1 for c in checks if c.status == "ok")
    warn = sum(1 for c in checks if c.status == "warn")
    fail = sum(1 for c in checks if c.status == "fail")
    print(f"Résumé: {ok} ok, {warn} avertissement(s), {fail} échec(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostic PHOEBUS")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args(argv)

    checks = run_checks()
    if args.json:
        print(json.dumps(checks_to_dicts(checks), ensure_ascii=False, indent=2))
    else:
        print_report(checks)
    return 1 if any(c.status == "fail" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
