# PHOEBUS/doctor.py
"""Diagnostic structuré de PHOEBUS.

OpenJarvis expose un `doctor` qui vérifie l'environnement avant de chercher des
bugs applicatifs. PHOEBUS reprend ce principe avec des checks adaptés au mode
voix/local : runtime unique, dépendances audio, STT, frontend, tokens et ports.
"""

from __future__ import annotations

import argparse
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
        "openai": "OpenAI/Groq/Mistral compatible",
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
            GROQ_API_KEY,
            OPENAI_API_KEY,
            PHOEBUS_WS_TOKEN,
            SERPAPI_API_KEY,
            TELEGRAM_TOKEN,
            WS_AUTH_REQUIRED,
            _secret_is_configured,
        )
    except Exception as exc:
        return [_fail("Configuration", f"import impossible: {exc}")]

    checks = [
        _ok("Port WebSocket", str(DEFAULT_WS_PORT)),
        _ok("Port mobile", str(DEFAULT_MOBILE_PORT)),
        _ok("Auth WebSocket", "active")
        if WS_AUTH_REQUIRED
        else _warn("Auth WebSocket", "désactivée"),
    ]
    if _secret_is_configured(PHOEBUS_WS_TOKEN):
        checks.append(_ok("Token WebSocket", "configuré"))
    else:
        checks.append(_fail("Token WebSocket", "placeholder ou absent"))

    providers = []
    if _secret_is_configured(GROQ_API_KEY):
        providers.append("groq")
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


def _check_stt() -> CheckResult:
    try:
        from PHOEBUS.stt_backends import get_backend

        backend = get_backend()
    except Exception as exc:
        return _fail("STT", f"erreur: {exc}")
    if not backend:
        return _fail("STT", "aucun backend disponible")
    return _ok("STT", backend[0])


def _check_runtime_singleton() -> CheckResult:
    try:
        result = _run(["pgrep", "-f", "[m]ain2.py --auto-restart"])
    except Exception as exc:
        return _warn("Runtime unique", f"non vérifié: {exc}")
    pids = [p for p in result.stdout.splitlines() if p.strip()]
    if len(pids) <= 1:
        return _ok("Runtime unique", f"{len(pids)} instance")
    return _fail("Runtime unique", f"{len(pids)} instances", "PID: " + ", ".join(pids))


def _check_frontend() -> list[CheckResult]:
    checks: list[CheckResult] = []
    npm = shutil.which("npm")
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


def run_checks() -> list[CheckResult]:
    checks = [_check_python()]
    checks.extend(_check_imports())
    checks.extend(_check_config())
    checks.append(_check_stt())
    checks.append(_check_runtime_singleton())
    checks.extend(_check_frontend())
    checks.append(_check_health_endpoint())
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
