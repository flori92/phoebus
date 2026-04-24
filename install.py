#!/usr/bin/env python3
"""
JARVIS — Script d'Installation Universel (One-Click)
Supporte : Windows 10/11, macOS 12+, Linux (Debian/Ubuntu, Fedora, Arch)

Étapes :
  1. Vérification Python 3.10+
  2. Dépendances système (portaudio, ffmpeg, unzip)
  3. Environnement virtuel .venv
  4. Fichiers de configuration (.env, jarvis_devices.json)
  5. Dossiers applicatifs
  6. Paquets Python (requirements.txt) avec gestion PyAudio Windows
  7. Modèle Vosk FR (wake word offline, ~40 Mo)
  8. Modèles OpenWakeWord (hey_jarvis, ~5 Mo, téléchargement auto)
  9. Interface Web (npm install, si Node.js présent)
  10. Raccourci Bureau
"""
import os
import sys
import platform
import shutil
import subprocess
import venv
import re
from pathlib import Path

ROOT         = Path(__file__).resolve().parent
VENV_DIR     = ROOT / ".venv"
MODELS_DIR   = ROOT / "models"
FRONTEND_DIR = ROOT / "frontend"

SYSTEM   = platform.system()          # "Windows" | "Darwin" | "Linux"
MACHINE  = platform.machine().lower() # "arm64", "x86_64", "amd64"…
IS_WIN   = SYSTEM == "Windows"
IS_MAC   = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"

# Vosk FR model
VOSK_FR_URL  = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"
VOSK_FR_ZIP  = MODELS_DIR / "vosk-model-small-fr-0.22.zip"
VOSK_FR_DIR  = MODELS_DIR / "vosk-model-small-fr-0.22"
VOSK_ENV_KEY = "JARVIS_VOSK_MODEL_PATH"

# ── Couleurs ─────────────────────────────────────────────────────────────────

class C:
    BLUE   = '\033[94m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

# Windows CMD ne supporte pas les codes ANSI sans activation explicite
if IS_WIN:
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
    except Exception:
        for attr in ("BLUE", "GREEN", "YELLOW", "RED", "BOLD", "END"):
            setattr(C, attr, "")

def step(msg):  print(f"\n{C.BLUE}{C.BOLD}==> {msg}{C.END}")
def ok(msg):    print(f"{C.GREEN}  ✓ {msg}{C.END}")
def warn(msg):  print(f"{C.YELLOW}  ⚠ {msg}{C.END}")
def fail(msg):  print(f"{C.RED}  ✗ {msg}{C.END}")
def info(msg):  print(f"    {msg}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list, cwd: Path = ROOT, check: bool = True, silent: bool = False) -> bool:
    """Lance une commande. Retourne True si succès."""
    try:
        kwargs: dict = {"cwd": str(cwd)}
        if silent:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        subprocess.run(cmd, check=check, **kwargs)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def pip(python_exe: Path, *args, silent=False) -> bool:
    return run([str(python_exe), "-m", "pip", *args], silent=silent)


def venv_python() -> Path:
    if IS_WIN:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


# ── 1. Python ─────────────────────────────────────────────────────────────────

def check_python():
    step("Vérification de Python")
    if sys.version_info < (3, 10):
        fail(f"Python 3.10+ requis. Version : {sys.version.split()[0]}")
        sys.exit(1)
    ok(f"Python {sys.version.split()[0]} — {SYSTEM} {platform.release()} ({MACHINE})")


# ── 2. Dépendances système ────────────────────────────────────────────────────

def install_system_deps():
    step(f"Dépendances système ({SYSTEM})")

    if IS_MAC:
        if not shutil.which("brew"):
            fail("Homebrew absent. Installez-le : https://brew.sh/ puis relancez.")
            sys.exit(1)
        run(["brew", "install", "portaudio", "ffmpeg", "unzip"], check=False)
        ok("portaudio, ffmpeg → OK (macOS/Homebrew)")

    elif IS_LINUX:
        if shutil.which("apt-get"):
            run(["sudo", "apt-get", "update", "-qq"], check=False)
            run(["sudo", "apt-get", "install", "-y", "-qq",
                 "portaudio19-dev", "ffmpeg", "unzip",
                 "python3-venv", "build-essential",
                 "libssl-dev", "libffi-dev"], check=False)
            ok("portaudio, ffmpeg → OK (Debian/Ubuntu/apt)")
        elif shutil.which("dnf"):
            run(["sudo", "dnf", "install", "-y",
                 "portaudio-devel", "ffmpeg", "unzip", "python3-devel"], check=False)
            ok("portaudio, ffmpeg → OK (Fedora/dnf)")
        elif shutil.which("pacman"):
            run(["sudo", "pacman", "-S", "--noconfirm",
                 "portaudio", "ffmpeg", "unzip"], check=False)
            ok("portaudio, ffmpeg → OK (Arch/pacman)")
        else:
            warn("Gestionnaire de paquets non reconnu. Installez manuellement : portaudio-dev, ffmpeg, unzip")

    elif IS_WIN:
        # Windows : ffmpeg optionnel (whisper en a besoin pour certains formats)
        if not shutil.which("ffmpeg"):
            warn("ffmpeg absent. Recommandé pour faster-whisper : https://ffmpeg.org/download.html")
        else:
            ok("ffmpeg déjà disponible.")
        ok("Pas de dépendances système supplémentaires requises sur Windows.")


# ── 3. Venv ───────────────────────────────────────────────────────────────────

def setup_venv() -> Path:
    step("Environnement virtuel Python (.venv)")
    if not VENV_DIR.exists():
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        ok(f"Venv créé dans {VENV_DIR.name}/")
    else:
        ok("Venv déjà présent.")
    return venv_python()


# ── 4. Configuration ──────────────────────────────────────────────────────────

def create_config_files():
    step("Fichiers de configuration")
    env_file, env_example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        ok(".env créé — ajoutez vos clés API.")
    else:
        ok(".env déjà présent.")

    dev_file, dev_example = ROOT / "jarvis_devices.json", ROOT / "jarvis_devices.example.json"
    if not dev_file.exists() and dev_example.exists():
        shutil.copyfile(dev_example, dev_file)
        ok("jarvis_devices.json créé.")
    else:
        ok("jarvis_devices.json déjà présent.")


# ── 5. Dossiers ───────────────────────────────────────────────────────────────

def setup_folders():
    step("Dossiers applicatifs")
    for d in ["logs", "models", "temp", "output", "jarvis_speaker_profiles"]:
        (ROOT / d).mkdir(exist_ok=True)
    ok("logs/, models/, temp/, output/, jarvis_speaker_profiles/ prêts.")


# ── 6. Paquets Python ─────────────────────────────────────────────────────────

def _install_pyaudio_windows(python_exe: Path) -> bool:
    """
    Sur Windows, PyAudio n'a pas de wheel officiel récent.
    On essaie dans l'ordre :
      1. pipwin  (installe le wheel pré-compilé depuis gohlke)
      2. wheel pré-compilé depuis Christoph Gohlke (unofficial)
      3. conda   (si Anaconda/Miniconda présent)
    """
    info("Installation de PyAudio sur Windows (stratégie spéciale)…")

    # Option 1 : pipwin
    pip(python_exe, "install", "pipwin", silent=True)
    if run([str(python_exe), "-m", "pipwin", "install", "pyaudio"], check=False, silent=True):
        ok("PyAudio installé via pipwin.")
        return True

    # Option 2 : wheel pré-compilé
    py_ver = f"{sys.version_info.major}{sys.version_info.minor}"
    arch   = "amd64" if "64" in MACHINE else "win32"
    wheel_url = (
        f"https://download.lfd.uci.edu/pythonlibs/archived/"
        f"PyAudio-0.2.14-cp{py_ver}-cp{py_ver}-win_{arch}.whl"
    )
    if pip(python_exe, "install", wheel_url, silent=True):
        ok("PyAudio installé depuis wheel Gohlke.")
        return True

    # Option 3 : conda
    conda = shutil.which("conda")
    if conda:
        if run([conda, "install", "-y", "pyaudio"], check=False, silent=True):
            ok("PyAudio installé via conda.")
            return True

    warn("PyAudio non installé sur Windows — le micro local est désactivé.")
    warn("Jarvis fonctionnera via l'interface web et mobile sans micro PC.")
    return False


def install_python_packages(python_exe: Path):
    step("Paquets Python (requirements.txt)")
    pip(python_exe, "install", "--upgrade", "pip", "setuptools", "wheel", silent=True)

    info("Installation de requirements.txt…")
    if pip(python_exe, "install", "-r", str(ROOT / "requirements.txt"), check=False):
        ok("Paquets installés.")
    else:
        warn("Installation groupée échouée — tentative paquet par paquet…")
        _install_one_by_one(python_exe)

    # PyAudio Windows : traitement spécial après les autres paquets
    if IS_WIN:
        _install_pyaudio_windows(python_exe)


def _install_one_by_one(python_exe: Path):
    req_file = ROOT / "requirements.txt"
    lines    = req_file.read_text(encoding="utf-8").splitlines()
    failed   = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = line.split(";")[0].strip()  # ignorer les marqueurs de plateforme ici
        if pip(python_exe, "install", line, check=False, silent=True):
            ok(f"  {pkg}")
        else:
            warn(f"  Échec : {pkg}")
            failed.append(pkg)
    if failed:
        warn(f"Paquets non installés : {', '.join(failed)}")


# ── 7. Modèle Vosk FR ─────────────────────────────────────────────────────────

def download_vosk_model():
    step("Modèle Vosk FR (wake word offline, ~40 Mo)")
    MODELS_DIR.mkdir(exist_ok=True)

    if VOSK_FR_DIR.exists():
        ok(f"Modèle déjà présent → {VOSK_FR_DIR.relative_to(ROOT)}/")
        _patch_env_vosk()
        return

    info(f"Téléchargement : {VOSK_FR_URL}")
    downloaded = False

    # curl (macOS/Linux natif, Windows optionnel)
    if shutil.which("curl"):
        downloaded = run(
            ["curl", "-L", "--progress-bar", "-o", str(VOSK_FR_ZIP), VOSK_FR_URL],
            check=False
        )
    # wget (Linux)
    if not downloaded and shutil.which("wget"):
        downloaded = run(
            ["wget", "-q", "--show-progress", "-O", str(VOSK_FR_ZIP), VOSK_FR_URL],
            check=False
        )
    # PowerShell fallback Windows
    if not downloaded and IS_WIN:
        ps_cmd = (
            f"Invoke-WebRequest -Uri '{VOSK_FR_URL}' "
            f"-OutFile '{VOSK_FR_ZIP}' -UseBasicParsing"
        )
        downloaded = run(
            ["powershell", "-Command", ps_cmd], check=False
        )
    # urllib Python pur (dernier recours, lent mais universel)
    if not downloaded:
        _download_urllib(VOSK_FR_URL, VOSK_FR_ZIP)
        downloaded = VOSK_FR_ZIP.exists()

    if not downloaded or not VOSK_FR_ZIP.exists():
        warn("Téléchargement Vosk échoué — wake word via OpenWakeWord à la place.")
        return

    # Extraction
    info("Extraction…")
    extracted = False
    # unzip natif (macOS/Linux)
    if shutil.which("unzip"):
        extracted = run(
            ["unzip", "-q", str(VOSK_FR_ZIP), "-d", str(MODELS_DIR)], check=False
        )
    # tar.zip via Python zipfile (cross-platform)
    if not extracted:
        import zipfile
        try:
            with zipfile.ZipFile(VOSK_FR_ZIP) as zf:
                zf.extractall(MODELS_DIR)
            extracted = True
        except Exception as e:
            warn(f"Extraction échouée : {e}")

    VOSK_FR_ZIP.unlink(missing_ok=True)

    if VOSK_FR_DIR.exists():
        ok(f"Modèle extrait → models/vosk-model-small-fr-0.22/")
        _patch_env_vosk()
    else:
        warn("Extraction échouée — wake word OpenWakeWord utilisé.")


def _download_urllib(url: str, dest: Path):
    try:
        import urllib.request
        info("Téléchargement urllib Python (peut prendre 1-2 min)…")

        def _progress(count, block, total):
            pct = min(100, int(count * block * 100 / (total or 1)))
            print(f"\r    {pct}%", end="", flush=True)

        urllib.request.urlretrieve(url, str(dest), reporthook=_progress)
        print()
    except Exception as e:
        warn(f"urllib échoué : {e}")


def _patch_env_vosk():
    """Met à jour JARVIS_VOSK_MODEL_PATH dans .env avec un chemin RELATIF portable."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    content  = env_file.read_text(encoding="utf-8")
    # Chemin relatif → fonctionne sur tous les OS
    rel_path = "models/vosk-model-small-fr-0.22"
    key_line = f"{VOSK_ENV_KEY}={rel_path}"

    if VOSK_ENV_KEY in content:
        content = re.sub(
            rf"^{VOSK_ENV_KEY}=.*$", key_line, content, flags=re.MULTILINE
        )
    else:
        content += f"\n{key_line}\n"
    env_file.write_text(content, encoding="utf-8")
    ok(f"{VOSK_ENV_KEY}={rel_path} → configuré dans .env")


# ── 8. Modèles OpenWakeWord ───────────────────────────────────────────────────

def download_oww_models(python_exe: Path):
    step("Modèles OpenWakeWord (hey_jarvis, ~5 Mo)")
    script = (
        "import openwakeword; "
        "openwakeword.utils.download_models(); "
        "print('OWW OK')"
    )
    if run([str(python_exe), "-c", script], check=False, silent=True):
        ok("Modèles OpenWakeWord téléchargés.")
    else:
        warn("Pré-téléchargement OWW échoué — sera fait au premier démarrage.")


# ── 9. Frontend ───────────────────────────────────────────────────────────────

def install_frontend():
    step("Interface Web (frontend)")
    if not FRONTEND_DIR.exists():
        warn("Dossier frontend/ absent — ignoré.")
        return
    npm = shutil.which("npm.cmd" if IS_WIN else "npm") or shutil.which("npm")
    if not npm:
        warn("npm absent. Installez Node.js LTS : https://nodejs.org/")
        return
    lock = FRONTEND_DIR / "package-lock.json"
    cmd  = [npm, "ci"] if lock.exists() else [npm, "install"]
    if run(cmd, cwd=FRONTEND_DIR, check=False):
        ok("Interface Web installée.")
    else:
        warn("npm install échoué — interface web partielle.")


# ── 10. Raccourci Bureau ──────────────────────────────────────────────────────

def create_shortcut():
    step("Raccourci Bureau")
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / "Bureau"  # Français
    if not desktop.exists():
        warn("Bureau introuvable — raccourci ignoré.")
        return
    try:
        if IS_WIN:
            p = desktop / "JARVIS.bat"
            p.write_text(
                f'@echo off\ncd /d "{ROOT}"\nstart cmd /k "DÉMARRER_JARVIS.bat"\n',
                encoding="utf-8"
            )
            ok("JARVIS.bat créé sur le Bureau Windows.")
        elif IS_MAC:
            p = desktop / "Démarrer JARVIS.command"
            p.write_text(f'#!/bin/bash\ncd "{ROOT}"\n./demarrer_jarvis.sh\n')
            os.chmod(p, 0o755)
            ok("'Démarrer JARVIS.command' créé sur le Bureau macOS.")
        elif IS_LINUX:
            p = desktop / "JARVIS.desktop"
            p.write_text(
                f"[Desktop Entry]\nName=J.A.R.V.I.S\n"
                f"Exec={ROOT}/demarrer_jarvis.sh\nTerminal=true\n"
                f"Type=Application\nIcon=utilities-terminal\n"
            )
            os.chmod(p, 0o755)
            ok("JARVIS.desktop créé sur le Bureau Linux.")
    except Exception as e:
        warn(f"Raccourci non créé : {e}")


# ── Résumé ────────────────────────────────────────────────────────────────────

def print_summary(python_exe: Path):
    vosk_status = (
        f"models/vosk-model-small-fr-0.22/" if VOSK_FR_DIR.exists() else "non téléchargé"
    )
    print(f"\n{C.GREEN}{C.BOLD}{'='*54}")
    print("  ✅  INSTALLATION TERMINÉE AVEC SUCCÈS !")
    print(f"{'='*54}{C.END}")
    print(f"\n  OS           : {SYSTEM} {platform.release()} ({MACHINE})")
    print(f"  Python       : {sys.version.split()[0]}")
    print(f"  Venv         : {VENV_DIR.relative_to(ROOT)}/")
    print(f"  Wake word OWW: modèle hey_jarvis prêt")
    print(f"  Wake word FR : {vosk_status}")
    print(f"  STT rapide   : faster-whisper")
    print(f"  Spotify      : spotipy (clé à configurer dans .env)")
    print(f"\n{C.YELLOW}Prochaines étapes :{C.END}")
    print(f"  1. Éditez {C.BOLD}.env{C.END} et ajoutez vos clés API")
    if IS_WIN:
        print(f"  2. Double-cliquez sur {C.BOLD}DÉMARRER_JARVIS.bat{C.END}")
    else:
        print(f"  2. Lancez : {C.BOLD}./demarrer_jarvis.sh{C.END}")
    print(f"  3. Diagnostic : {C.BOLD}{python_exe} scripts/diagnose.py{C.END}\n")


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    print(f"\n{C.BLUE}{C.BOLD}{'='*54}")
    print("    INSTALLATEUR UNIVERSEL J.A.R.V.I.S")
    print(f"    Windows · macOS · Linux")
    print(f"{'='*54}{C.END}\n")

    check_python()
    install_system_deps()
    python_exe = setup_venv()
    create_config_files()
    setup_folders()
    install_python_packages(python_exe)
    download_vosk_model()
    download_oww_models(python_exe)
    install_frontend()
    create_shortcut()
    print_summary(python_exe)


if __name__ == "__main__":
    main()
