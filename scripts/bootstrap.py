#!/usr/bin/env python3
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
FRONTEND_DIR = ROOT / "frontend"


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd), check=check)


def venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    if not VENV_DIR.exists():
        print(f"[BOOTSTRAP] Creation de l'environnement Python: {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    return venv_python()


def install_python_deps(py: Path) -> None:
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(py), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])

    optional = ROOT / "requirements-optional.txt"
    if optional.exists():
        result = run([str(py), "-m", "pip", "install", "-r", str(optional)], check=False)
        if result.returncode != 0:
            print()
            print("[BOOTSTRAP] PyAudio n'a pas pu etre installe automatiquement.")
            print("[BOOTSTRAP] Ce n'est pas bloquant: le mobile et le backend restent utilisables.")
            if platform.system() == "Darwin":
                print("[BOOTSTRAP] Pour activer le micro PC sur macOS: brew install portaudio puis relancer ce script.")
            elif platform.system() == "Linux":
                print("[BOOTSTRAP] Pour activer le micro PC sur Linux: installez portaudio19-dev puis relancez ce script.")


def install_frontend() -> None:
    if not FRONTEND_DIR.exists():
        print("[BOOTSTRAP] Aucun dossier frontend/, etape ignoree.")
        return
    npm = shutil.which("npm.cmd" if platform.system() == "Windows" else "npm") or shutil.which("npm")
    if not npm:
        print("[BOOTSTRAP] npm introuvable. Installez Node.js LTS pour l'interface web.")
        return

    lock = FRONTEND_DIR / "package-lock.json"
    if lock.exists():
        result = run([npm, "ci"], cwd=FRONTEND_DIR, check=False)
        if result.returncode == 0:
            return
        print("[BOOTSTRAP] npm ci a echoue, tentative npm install.")
    run([npm, "install"], cwd=FRONTEND_DIR)


def ensure_env_template() -> None:
    env_file = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copyfile(example, env_file)
        print("[BOOTSTRAP] .env cree depuis .env.example. Renseignez vos cles avant d'utiliser les fonctions cloud.")


def main() -> int:
    print("[BOOTSTRAP] J.A.R.V.I.S")
    print(f"[BOOTSTRAP] OS: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"[BOOTSTRAP] Python: {sys.version.split()[0]}")

    if sys.version_info < (3, 10):
        print("[BOOTSTRAP] Python 3.10+ est requis.")
        return 1

    ensure_env_template()
    py = ensure_venv()
    install_python_deps(py)
    install_frontend()

    print()
    print("[BOOTSTRAP] Installation terminee.")
    print(f"[BOOTSTRAP] Diagnostic: {py} scripts/diagnose.py")
    print(f"[BOOTSTRAP] Lancement : {py} main2.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
