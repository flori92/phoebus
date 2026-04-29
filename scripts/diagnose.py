#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

REQUIRED_IMPORTS = {
    "dotenv": "python-dotenv",
    "edge_tts": "edge-tts",
    "google.genai": "google-genai",
    "googleapiclient.discovery": "google-api-python-client",
    "openai": "openai",
    "PIL": "Pillow",
    "pyautogui": "PyAutoGUI",
    "pygame": "pygame",
    "requests": "requests",
    "speech_recognition": "SpeechRecognition",
    "websockets": "websockets",
}

OPTIONAL_IMPORTS = {
    "pyaudio": "PyAudio, requis pour micro PC et detection des applaudissements",
}

ENV_RULES = {
    "GEMINI_API_KEY": lambda value: bool(value and value != "VOTRE_CLE_ICI"),
    "YOUTUBE_API_KEY": lambda value: bool(value and value != "VOTRE_CLE_ICI"),
    "HA_URL": lambda value: bool(value and value != "http://homeassistant.local:8123"),
    "HA_TOKEN": lambda value: bool(value and value != "VOTRE_TOKEN_ICI"),
    "SERPAPI_API_KEY": lambda value: bool(value and value != "VOTRE_CLE_ICI"),
    "GROQ_API_KEY": lambda value: bool(value and value != "VOTRE_CLE_ICI"),
    "MISTRAL_API_KEY": lambda value: bool(value and value != "VOTRE_CLE_ICI"),
    "PHOEBUS_WS_TOKEN": lambda value: bool(value and value not in {"CHANGE_ME", "VOTRE_TOKEN_ICI"}),
    "PHOEBUS_DEVICES_FILE": lambda value: True,
    "PHOEBUS_AUDIT_FILE": lambda value: True,
    "PHOEBUS_BRAIN_MODE": lambda value: (value or "balanced")
    in {"balanced", "speed", "smart", "privacy", "local_first"},
    "PHOEBUS_BRAIN_ORDER": lambda value: True,
    "PHOEBUS_GEMINI_MODELS": lambda value: True,
    "PHOEBUS_OLLAMA_MODELS": lambda value: True,
    "PHOEBUS_WAKE_ENABLED": lambda value: (value or "0").lower()
    in {"0", "1", "true", "false", "yes", "no", "on", "off"},
}


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def print_check(ok: bool, label: str, detail: str = "") -> None:
    marker = "OK " if ok else "KO "
    suffix = f" - {detail}" if detail else ""
    print(f"[{marker}] {label}{suffix}")


def main() -> int:
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    print("Diagnostic J.A.R.V.I.S")
    print(f"Racine : {ROOT}")
    print(f"OS     : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python : {sys.version.split()[0]}")
    print()

    failed = False
    for module, package in REQUIRED_IMPORTS.items():
        ok = has_module(module)
        print_check(ok, module, package)
        failed = failed or not ok

    for module, detail in OPTIONAL_IMPORTS.items():
        print_check(has_module(module), module, detail)

    print()
    for key, rule in ENV_RULES.items():
        value = os.getenv(key)
        configured = rule(value)
        print_check(configured, f"env {key}", "optionnel selon les fonctions utilisees")

    print()
    print_check(
        (ROOT / "phoebus_devices.example.json").exists(),
        "phoebus_devices.example.json",
        "modele d'alias Home Assistant",
    )
    local_devices = ROOT / "phoebus_devices.json"
    print_check(
        local_devices.exists(), "phoebus_devices.json", "copie locale recommandee pour les alias HA"
    )
    print_check((ROOT / ".env.example").exists(), ".env.example", "modele de configuration")

    print()
    npm = shutil.which("npm.cmd" if platform.system() == "Windows" else "npm") or shutil.which(
        "npm"
    )
    print_check(bool(npm), "npm", npm or "installez Node.js LTS")
    if npm and (ROOT / "frontend" / "package.json").exists():
        result = subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend")
        print_check(result.returncode == 0, "frontend build")
        failed = failed or result.returncode != 0

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
