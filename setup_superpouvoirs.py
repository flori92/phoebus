#!/usr/bin/env python3
\"\"\"
PHOEBUS Superpouvoirs — Script Setup Automatique

Ce script configure et lance PHOEBUS avec tous les 7 super-pouvoirs activés.
Exécution: python install.py superpouvoirs
\"\"\"

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Tuple


class PHOEBUSSetup:
    \"\"\"Gestionnaire de configuration PHOEBUS.\"\"\"
    
    def __init__(self):
        self.root = Path(__file__).parent
        self.os_type = sys.platform
        self.errors = []
        self.warnings = []
    
    def log_info(self, msg: str):
        print(f\"✅ {msg}\")
    
    def log_warn(self, msg: str):
        print(f\"⚠️  {msg}\")
        self.warnings.append(msg)
    
    def log_error(self, msg: str):
        print(f\"❌ {msg}\")
        self.errors.append(msg)
    
    def run_cmd(self, cmd: List[str], description: str = \"\") -> Tuple[int, str]:
        \"\"\"Exécute une commande shell.\"\"\"
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            self.log_error(f\"Timeout: {description}\")
            return -1, \"Timeout\"
        except Exception as e:
            self.log_error(f\"Erreur: {description}: {e}\")
            return -1, str(e)
    
    def check_python_version(self) -> bool:
        \"\"\"Vérifie Python >= 3.9.\"\"\"
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 9):
            self.log_error(f\"Python 3.9+ requis (actuellement {version.major}.{version.minor})\")
            return False
        self.log_info(f\"Python {version.major}.{version.minor}.{version.micro} OK\")
        return True
    
    def check_venv(self) -> bool:
        \"\"\"Vérifie que nous sommes dans un venv.\"\"\"
        if not hasattr(sys, 'real_prefix') and sys.prefix == sys.base_prefix:
            self.log_warn(\"Pas dans un venv. Créer avec: python3 -m venv .venv\")
            return False
        self.log_info(\"Virtual environment actif\")
        return True
    
    def install_system_deps_mac(self) -> bool:
        \"\"\"Installe dépendances système macOS.\"\"\"
        self.log_info(\"Vérification dépendances macOS...\")
        
        deps = {
            \"portaudio\": \"Audio processing\",
            \"cmake\": \"Build tools\",
            \"pkg-config\": \"Package config\",
        }
        
        for dep, desc in deps.items():
            code, _ = self.run_cmd([\"brew\", \"list\", dep], f\"Check {dep}\")
            if code != 0:
                self.log_info(f\"Installation {dep} ({desc})...\")
                code, out = self.run_cmd([\"brew\", \"install\", dep], f\"Install {dep}\")
                if code != 0:
                    self.log_error(f\"Impossible d'installer {dep}: {out}\")
                    return False
                self.log_info(f\"{dep} installé\")
            else:
                self.log_info(f\"{dep} déjà installé\")
        
        return True
    
    def install_python_deps(self) -> bool:
        \"\"\"Installe les dépendances Python (audio, vision, IA).\"\"\"
        self.log_info(\"Installation dépendances Python...\")
        
        # Dépendances critiques
        critical_packages = [
            \"webrtcvad\",           # VAD robuste
            \"faster-whisper\",      # STT rapide
            \"opencv-python\",       # Vision
            \"numpy\",              # Calculs
            \"Pillow\",             # Images
            \"soundfile\",          # Audio
        ]
        
        # Dépendances optionnelles
        optional_packages = [
            \"silero-vad\",         # Fallback VAD
            \"resemblyzer\",        # Reconnaissance vocale
            \"torch\",              # ML (pour Silero)
        ]
        
        all_packages = critical_packages + optional_packages
        
        # Installer avec pip
        for package in all_packages:
            self.log_info(f\"Installation {package}...\")
            code, out = self.run_cmd(
                [sys.executable, \"-m\", \"pip\", \"install\", \"-U\", package],
                f\"Install {package}\"
            )
            if code != 0:
                if package in critical_packages:
                    self.log_error(f\"Impossible d'installer {package}\")
                    return False
                else:
                    self.log_warn(f\"Impossible d'installer {package} (optionnel)\")
        
        return True
    
    def setup_env_file(self) -> bool:
        \"\"\"Configure le fichier .env avec les super-pouvoirs.\"\"\"
        self.log_info(\"Configuration .env...\")
        
        env_file = self.root / \".env\"
        env_superpouvoirs = self.root / \".env.phoebus-superpouvoirs\"\n        
        if not env_superpouvoirs.exists():
            self.log_error(\".env.phoebus-superpouvoirs non trouvé\")
            return False
        
        # Copier fichier de configuration
        if env_file.exists():
            backup = env_file.with_suffix(\".env.backup\")
            self.log_info(f\"Sauvegarde .env → {backup.name}\")
            env_file.rename(backup)
        
        # Copier configuration optimisée
        env_superpouvoirs.rename(env_file) if not env_file.exists() else None
        content = env_superpouvoirs.read_text()
        env_file.write_text(content)
        
        self.log_info(\".env configuré avec les super-pouvoirs\")
        return True
    
    def test_audio(self) -> bool:
        \"\"\"Test le module audio.\"\"\"
        self.log_info(\"Test audio optimization...\")
        try:
            from PHOEBUS.audio_optimization import check_hallucination
            
            # Test 1: Hallucination
            is_hall, conf = check_hallucination(\"Merci de votre écoute\")
            if is_hall and conf < 0.3:
                self.log_info(\"Détection hallucination: OK ✓\")
            else:
                self.log_warn(\"Détection hallucination: résultat inattendu\")
            
            # Test 2: Texte normal
            is_hall2, conf2 = check_hallucination(\"Bonjour comment ça va\")
            if not is_hall2 and conf2 > 0.7:
                self.log_info(\"Confiance texte normal: OK ✓\")
            else:
                self.log_warn(\"Confiance texte normal: résultat inattendu\")
            
            return True
        except Exception as e:
            self.log_error(f\"Erreur test audio: {e}\")
            return False
    
    def test_cameras(self) -> bool:
        \"\"\"Test découverte caméras.\"\"\"
        self.log_info(\"Test découverte caméras...\")
        try:
            from PHOEBUS.network_cameras import discover_cameras
            
            cameras = discover_cameras(scan_network=False)  # Sans scan réseau (trop lent)
            self.log_info(f\"Caméras disponibles: {len(cameras)} ✓\")
            for cam in cameras:
                self.log_info(f\"  • {cam.get('name')}\")
            return True
        except Exception as e:
            self.log_error(f\"Erreur test caméras: {e}\")
            return False
    
    def test_lmarena(self) -> bool:
        \"\"\"Vérifie si LMArena est disponible.\"\"\"
        self.log_info(\"Vérification LMArena Bridge...\")
        
        arena_dir = self.root / \"external\" / \"LMArenaBridge\"\n        if arena_dir.exists():
            self.log_info(\"LMArenaBridge trouvé ✓\")
            config = arena_dir / \"config.json\"\n            if config.exists():
                self.log_info(\"Configuration LMArenaBridge trouvée ✓\")
            else:
                self.log_warn(\"config.json manquant - voir GUIDE_SUPERPOUVOIRS.md\")
            return True
        else:
            self.log_warn(\"LMArenaBridge pas encore cloné - voir GUIDE_SUPERPOUVOIRS.md\")\n            return False
    
    def create_log_dirs(self) -> bool:
        \"\"\"Crée les répertoires de logs.\"\"\"
        logs_dir = self.root / \"logs\"\n        logs_dir.mkdir(exist_ok=True)
        (logs_dir / \"arena_bridge.log\").touch(exist_ok=True)
        self.log_info(\"Répertoires logs créés ✓\")
        return True
    
    def run_full_setup(self) -> bool:
        \"\"\"Exécute la configuration complète.\"\"\"
        print(\"\\n\" + \"=\"*60)
        print(\"🌟 PHOEBUS SUPERPOUVOIRS — Configuration Automatique\")\n        print(\"=\"*60 + \"\\n\")\n        
        steps = [\n            (\"Python\", self.check_python_version),\n            (\"Virtual Env\", self.check_venv),\n            (\"Dépendances Système\", self.install_system_deps_mac if self.os_type == \"darwin\" else lambda: True),\n            (\"Dépendances Python\", self.install_python_deps),\n            (\"Configuration .env\", self.setup_env_file),\n            (\"Logs\", self.create_log_dirs),\n            (\"Test Audio\", self.test_audio),\n            (\"Test Caméras\", self.test_cameras),\n            (\"LMArena\", self.test_lmarena),\n        ]\n        
        print(f\"\\n📋 Étapes: {len(steps)}\\n\")\n        
        for i, (name, func) in enumerate(steps, 1):
            print(f\"[{i}/{len(steps)}] {name}...\")\n            try:
                if func():
                    continue
                else:
                    self.log_error(f\"Échec: {name}\")\n                    return False
            except Exception as e:
                self.log_error(f\"Exception: {name}: {e}\")\n                return False
            print()\n        
        return True
    
    def print_summary(self):
        \"\"\"Affiche un résumé final.\"\"\"
        print(\"\\n\" + \"=\"*60)
        print(\"📊 RÉSUMÉ CONFIGURATION\")\n        print(\"=\"*60 + \"\\n\")\n        
        if not self.errors:
            print(\"✅ Configuration COMPLÈTE et RÉUSSIE!\\n\")\n        else:
            print(f\"⚠️  {len(self.errors)} erreur(s), {len(self.warnings)} avertissement(s)\\n\")\n        
        if self.warnings:
            print(\"⚠️  Avertissements:\")\n            for w in self.warnings:
                print(f\"   • {w}\")\n        
        if self.errors:
            print(\"\\n❌ Erreurs:\")\n            for e in self.errors:
                print(f\"   • {e}\")\n        
        print(\"\\n📚 Docs:\")\n        print(\"   • Diagnostic: DIAGNOSTIC_PHOEBUS_COMPLETE.md\")\n        print(\"   • Guide: GUIDE_SUPERPOUVOIRS.md\")\n        print(\"   • Config: .env.phoebus-superpouvoirs\")\n        print()\n        print(\"🚀 Démarrer PHOEBUS:\")\n        print(\"   python main2.py\")\n        print()\n\nif __name__ == \"__main__\":\n    setup = PHOEBUSSetup()\n    success = setup.run_full_setup()\n    setup.print_summary()\n    sys.exit(0 if success else 1)\n