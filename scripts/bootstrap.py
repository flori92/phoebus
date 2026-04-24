#!/usr/bin/env python3
"""
JARVIS — Bootstrap (lanceur rapide depuis demarrer_jarvis.sh / DÉMARRER_JARVIS.bat)

Vérifie que le venv et les paquets sont présents, sinon lance l'installation.
Plus léger que install.py : appelé à chaque démarrage.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT         = Path(__file__).resolve().parents[1]
VENV_DIR     = ROOT / ".venv"
MODELS_DIR   = ROOT / "models"
FRONTEND_DIR = ROOT / "frontend"

SYSTEM  = platform.system()
IS_WIN  = SYSTEM == "Windows"
IS_MAC  = SYSTEM == "Darwin"


def venv_python() -> Path:
    if IS_WIN:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], cwd=str(cwd), check=check)


def ensure_venv() -> Path:
    if not VENV_DIR.exists():
        print(f"[BOOTSTRAP] Création de l'environnement Python : {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    return venv_python()


def install_system_deps() -> None:
    if IS_MAC:
        if shutil.which("brew"):
            print("[BOOTSTRAP] Vérification portaudio (macOS)…")
            run(["brew", "install", "portaudio", "ffmpeg"], check=False)
        else:
            print("[BOOTSTRAP] ⚠ Homebrew absent. Micro PC désactivé.")
    elif SYSTEM == "Linux":
        if shutil.which("apt-get"):
            print("[BOOTSTRAP] Vérification portaudio (Linux/apt)…")
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "-qq", "portaudio19-dev", "ffmpeg"],
                check=False
            )
        elif shutil.which("dnf"):
            subprocess.run(
                ["sudo", "dnf", "install", "-y", "portaudio-devel", "ffmpeg"],
                check=False
            )
        elif shutil.which("pacman"):
            subprocess.run(
                ["sudo", "pacman", "-S", "--noconfirm", "portaudio", "ffmpeg"],
                check=False
            )
    elif IS_WIN:
        if not shutil.which("ffmpeg"):
            print("[BOOTSTRAP] ⚠ ffmpeg absent. Recommandé pour faster-whisper.")


def _install_pyaudio_windows(py: Path) -> None:
    """Tente pipwin, puis wheel Gohlke, puis conda."""
    subprocess.run([str(py), "-m", "pip", "install", "pipwin"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run([str(py), "-m", "pipwin", "install", "pyaudio"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode == 0:
        print("[BOOTSTRAP] ✓ PyAudio installé via pipwin.")
        return
    py_ver = f"{sys.version_info.major}{sys.version_info.minor}"
    arch   = "amd64" if "64" in platform.machine() else "win32"
    wheel  = (
        f"https://download.lfd.uci.edu/pythonlibs/archived/"
        f"PyAudio-0.2.14-cp{py_ver}-cp{py_ver}-win_{arch}.whl"
    )
    r2 = subprocess.run([str(py), "-m", "pip", "install", wheel],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r2.returncode == 0:
        print("[BOOTSTRAP] ✓ PyAudio installé (wheel Gohlke).")
        return
    print("[BOOTSTRAP] ⚠ PyAudio non installé — micro PC désactivé (non bloquant).")


def install_python_deps(py: Path) -> None:
    run([py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    result = run([py, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=False)
    if result.returncode != 0:
        print()
        print("[BOOTSTRAP] ⚠ Certains paquets n'ont pas pu être installés.")
        if IS_MAC:
            print("[BOOTSTRAP]   Pour PyAudio sur macOS : brew install portaudio puis relancez.")
        elif SYSTEM == "Linux":
            print("[BOOTSTRAP]   Pour PyAudio sur Linux : sudo apt install portaudio19-dev puis relancez.")
        elif IS_WIN:
            _install_pyaudio_windows(py)

    # Vosk : vérifier si le modèle FR est présent, sinon informer
    vosk_dir = MODELS_DIR / "vosk-model-small-fr-0.22"
    if not vosk_dir.exists():
        print("[BOOTSTRAP] ⚠ Modèle Vosk FR absent.")
        print("[BOOTSTRAP]   Lancez : python install.py  pour le télécharger automatiquement.")
        print("[BOOTSTRAP]   Wake word OpenWakeWord utilisé en attendant.")


def install_frontend() -> None:
    if not FRONTEND_DIR.exists():
        print("[BOOTSTRAP] Aucun dossier frontend/, étape ignorée.")
        return
    npm = shutil.which("npm.cmd" if IS_WIN else "npm") or shutil.which("npm")
    if not npm:
        print("[BOOTSTRAP] npm introuvable. Installez Node.js LTS : https://nodejs.org/")
        return
    lock = FRONTEND_DIR / "package-lock.json"
    cmd  = [npm, "ci"] if lock.exists() else [npm, "install"]
    r = run(cmd, cwd=FRONTEND_DIR, check=False)
    if r.returncode != 0:
        print("[BOOTSTRAP] npm install a échoué — interface web peut ne pas fonctionner.")


def ensure_env_template() -> None:
    env_file = ROOT / ".env"
    example  = ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        import shutil as _sh
        _sh.copyfile(example, env_file)
        print("[BOOTSTRAP] .env créé depuis .env.example. Renseignez vos clés avant de démarrer.")


def ensure_devices_template() -> None:
    target  = ROOT / "jarvis_devices.json"
    example = ROOT / "jarvis_devices.example.json"
    if not target.exists() and example.exists():
        import shutil as _sh
        _sh.copyfile(example, target)
        print("[BOOTSTRAP] jarvis_devices.json créé depuis l'exemple.")


def main() -> int:
    print("[BOOTSTRAP] J.A.R.V.I.S")
    print(f"[BOOTSTRAP] OS    : {SYSTEM} {platform.release()} ({platform.machine()})")
    print(f"[BOOTSTRAP] Python: {sys.version.split()[0]}")

    if sys.version_info < (3, 10):
        print("[BOOTSTRAP] ✗ Python 3.10+ requis.")
        return 1

    ensure_env_template()
    ensure_devices_template()
    for d in ["logs", "models", "temp", "output", "jarvis_speaker_profiles"]:
        (ROOT / d).mkdir(exist_ok=True)

    install_system_deps()
    py = ensure_venv()
    install_python_deps(py)
    install_frontend()

    print()
    print("[BOOTSTRAP] ✓ Prêt.")
    print(f"[BOOTSTRAP] Diagnostic : {py} scripts/diagnose.py")
    print(f"[BOOTSTRAP] Lancement  : {py} main2.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
