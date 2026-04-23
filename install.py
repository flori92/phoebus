#!/usr/bin/env python3
"""
JARVIS - Script d'Installation Universel (One-Click)
Ce script détecte l'OS (Windows, macOS, Linux) et configure automatiquement tout l'environnement.
"""
import os
import sys
import platform
import shutil
import subprocess
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
FRONTEND_DIR = ROOT / "frontend"

# Couleurs pour le terminal
class C:
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(msg):
    print(f"\n{C.OKBLUE}{C.BOLD}==> {msg}{C.ENDC}")

def print_success(msg):
    print(f"{C.OKGREEN}✓ {msg}{C.ENDC}")

def print_error(msg):
    print(f"{C.FAIL}✗ {msg}{C.ENDC}")

def run_cmd(cmd, cwd=ROOT, check=True):
    try:
        subprocess.run(cmd, cwd=str(cwd), check=check)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Erreur lors de l'exécution de: {' '.join(cmd)}")
        return False

def check_python_version():
    print_step("Vérification de la version Python")
    if sys.version_info < (3, 10):
        print_error(f"Python 3.10+ est requis. Version actuelle : {sys.version.split()[0]}")
        sys.exit(1)
    print_success(f"Python {sys.version.split()[0]} détecté.")

def install_system_dependencies():
    sys_name = platform.system()
    print_step(f"Installation des dépendances système pour {sys_name}")
    
    if sys_name == "Darwin":
        if not shutil.which("brew"):
            print_error("Homebrew n'est pas installé. Veuillez l'installer depuis https://brew.sh/")
            sys.exit(1)
        print("Vérification de portaudio (requis pour le micro)...")
        run_cmd(["brew", "install", "portaudio", "ffmpeg"], check=False)
        print_success("Dépendances macOS à jour.")
        
    elif sys_name == "Linux":
        if shutil.which("apt-get"):
            print("Vérification des dépendances APT (portaudio, ffmpeg)...")
            run_cmd(["sudo", "apt-get", "update"], check=False)
            run_cmd(["sudo", "apt-get", "install", "-y", "portaudio19-dev", "ffmpeg", "python3-venv"], check=False)
            print_success("Dépendances Linux (Debian/Ubuntu) à jour.")
        else:
            print_error("Gestionnaire de paquets non supporté automatiquement (APT requis). Installez manuellement portaudio.")
            
    elif sys_name == "Windows":
        print_success("Aucune dépendance système complexe requise pour Windows.")

def setup_virtual_env():
    print_step("Création de l'environnement virtuel Python")
    if not VENV_DIR.exists():
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        print_success(f"Environnement créé dans {VENV_DIR.name}/")
    else:
        print_success("L'environnement virtuel existe déjà.")
        
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def install_python_packages(python_exe):
    print_step("Installation des paquets Python (requirements.txt)")
    run_cmd([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    success = run_cmd([str(python_exe), "-m", "pip", "install", "-r", "requirements.txt"])
    if success:
        print_success("Paquets Python installés avec succès.")
    else:
        print_error("L'installation des paquets Python a échoué.")
        sys.exit(1)

def install_frontend_dependencies():
    print_step("Installation des dépendances du Frontend Web (Interface)")
    if not FRONTEND_DIR.exists():
        print_error("Dossier frontend/ introuvable. Étape ignorée.")
        return
        
    npm = shutil.which("npm.cmd" if platform.system() == "Windows" else "npm")
    if not npm:
        print_error("Node.js / npm n'est pas installé. Veuillez installer Node.js pour utiliser l'interface Web.")
        return
        
    print("Exécution de npm install...")
    success = run_cmd([npm, "install"], cwd=FRONTEND_DIR)
    if success:
        print_success("Interface Web prête.")
    else:
        print_error("L'installation NPM a échoué.")

def create_configuration_files():
    print_step("Configuration initiale")
    
    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        print_success("Fichier .env créé. Pensez à y ajouter vos clés API.")
    else:
        print_success("Fichier .env déjà présent.")
        
    devices_file = ROOT / "jarvis_devices.json"
    devices_example = ROOT / "jarvis_devices.example.json"
    if not devices_file.exists() and devices_example.exists():
        shutil.copyfile(devices_example, devices_file)
        print_success("Fichier jarvis_devices.json créé. Personnalisez vos pièces ici.")
    else:
        print_success("Fichier jarvis_devices.json déjà présent.")

def setup_application_folders():
    print_step("Création des dossiers d'application")
    folders = ["logs", "jarvis_vector_db", "temp"]
    for folder in folders:
        path = ROOT / folder
        path.mkdir(exist_ok=True)
    print_success("Dossiers logs/, jarvis_vector_db/ et temp/ prêts.")

def create_desktop_shortcuts():
    print_step("Création des raccourcis sur le Bureau")
    sys_name = platform.system()
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / "Bureau"
    
    if not desktop.exists():
        print_success("Dossier Bureau introuvable. Raccourcis ignorés.")
        return

    try:
        if sys_name == "Windows":
            # Création d'un petit script .bat sur le bureau
            shortcut_path = desktop / "JARVIS.bat"
            with open(shortcut_path, "w") as f:
                f.write(f'@echo off\ncd /d "{ROOT}"\nstart cmd /k "DÉMARRER_JARVIS.bat"\n')
            print_success("Raccourci JARVIS.bat créé sur le Bureau Windows.")
            
        elif sys_name == "Darwin":
            # Création d'un script exécutable sur le bureau Mac
            shortcut_path = desktop / "Démarrer JARVIS.command"
            with open(shortcut_path, "w") as f:
                f.write(f'#!/bin/bash\ncd "{ROOT}"\n./demarrer_jarvis.sh\n')
            os.chmod(shortcut_path, 0o755)
            print_success("Raccourci 'Démarrer JARVIS.command' créé sur le Bureau Mac.")
            
        elif sys_name == "Linux":
            # Création d'un fichier .desktop pour Linux
            shortcut_path = desktop / "JARVIS.desktop"
            with open(shortcut_path, "w") as f:
                f.write(f"[Desktop Entry]\nName=J.A.R.V.I.S\nExec={ROOT}/demarrer_jarvis.sh\nTerminal=true\nType=Application\nIcon=utilities-terminal\n")
            os.chmod(shortcut_path, 0o755)
            print_success("Raccourci JARVIS.desktop créé sur le Bureau Linux.")
            
    except Exception as e:
        print_error(f"Erreur lors de la création du raccourci : {e}")

def main():
    print(f"\n{C.OKBLUE}{C.BOLD}==========================================")
    print(" INSTALLATEUR UNIVERSEL J.A.R.V.I.S")
    print(f"=========================================={C.ENDC}")
    
    check_python_version()
    install_system_dependencies()
    python_exe = setup_virtual_env()
    install_python_packages(python_exe)
    install_frontend_dependencies()
    create_configuration_files()
    setup_application_folders()
    create_desktop_shortcuts()
    
    print(f"\n{C.OKGREEN}{C.BOLD}==========================================")
    print(" INSTALLATION TERMINÉE AVEC SUCCÈS !")
    print(f"=========================================={C.ENDC}")
    print("\nPour démarrer JARVIS :")
    if platform.system() == "Windows":
        print(f"   {C.WARNING}Double-cliquez sur DÉMARRER_JARVIS.bat{C.ENDC}")
    else:
        print(f"   {C.WARNING}./demarrer_jarvis.sh{C.ENDC} ou {C.WARNING}python3 main2.py{C.ENDC}\n")

if __name__ == "__main__":
    main()
