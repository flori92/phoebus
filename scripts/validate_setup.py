#!/usr/bin/env python3
"""
Script de validation du setup de développement PHOEBUS.
Vérifie que tous les outils sont correctement installés.
"""
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, description):
    """Exécute une commande et retourne le résultat."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def check_python_version():
    """Vérifie Python >= 3.11."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor} (besoin de 3.11+)")
        return False


def check_package(package_name):
    """Vérifie si un package est installé."""
    try:
        __import__(package_name)
        print(f"✅ {package_name}")
        return True
    except ImportError:
        print(f"❌ {package_name} (pip install {package_name})")
        return False


def check_tool(command, tool_name):
    """Vérifie si un outil CLI est disponible."""
    success, _, _ = run_cmd([command, "--version"], tool_name)
    if success:
        print(f"✅ {tool_name}")
        return True
    else:
        print(f"❌ {tool_name}")
        return False


def main():
    """Validation complète."""
    print("🚀 Validation Setup PHOEBUS\n")
    
    all_ok = True
    
    # 1. Python
    print("📦 Environnement Python:")
    all_ok &= check_python_version()
    
    # 2. Packages essentiels
    print("\n📦 Packages requis:")
    packages = ["pytest", "pydantic", "pydantic_settings", "black", "isort", "mypy", "flake8"]
    for pkg in packages:
        all_ok &= check_package(pkg)
    
    # 3. Outils CLI
    print("\n🔧 Outils CLI:")
    tools = [
        ("black", "Black formatter"),
        ("isort", "isort import sorter"),
        ("mypy", "MyPy type checker"),
        ("flake8", "Flake8 linter"),
        ("pytest", "Pytest"),
    ]
    for cmd, name in tools:
        all_ok &= check_tool(cmd, name)
    
    # 4. Structure projet
    print("\n📁 Structure projet:")
    required_files = [
        "pytest.ini",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        ".github/workflows/ci.yml",
        "PHOEBUS/config_pydantic.py",
        "tests/conftest.py",
    ]
    root = Path(__file__).parent.parent
    for f in required_files:
        path = root / f
        if path.exists():
            print(f"✅ {f}")
        else:
            print(f"❌ {f} (manquant)")
            all_ok = False
    
    # 5. Tests
    print("\n🧪 Tests:")
    success, stdout, stderr = run_cmd(["python", "-m", "pytest", "tests/", "-v", "--tb=short"], "Tests")
    if success:
        print("✅ Tests passent")
    else:
        print("⚠️  Tests échouent (normal si pas encore de code)")
        if "no tests ran" in stdout.lower() or "no tests ran" in stderr.lower():
            print("   ℹ️  Aucun test trouvé - à implémenter")
        else:
            all_ok = False
    
    # Résumé
    print("\n" + "="*50)
    if all_ok:
        print("🎉 Setup complet! Prêt pour le développement.")
        print("\nProchaines étapes:")
        print("  1. pip install pre-commit && pre-commit install")
        print("  2. pytest tests/  # Lancer les tests")
        print("  3. black PHOEBUS/ tests/  # Formatter le code")
        return 0
    else:
        print("⚠️  Setup incomplet. Installez les dépendances manquantes:")
        print("   pip install -e '.[dev]'")
        return 1


if __name__ == "__main__":
    sys.exit(main())
