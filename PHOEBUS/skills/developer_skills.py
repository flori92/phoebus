# PHOEBUS/skills/developer_skills.py
"""Compétences Agentiques — Permet à PHOEBUS d'écrire son propre code.

Fournit la capacité de :
- Créer de nouveaux skills à la volée (qui s'enregistrent instantanément)
- Exécuter des commandes terminal (pour installer des dépendances, etc.)
"""

import os
import subprocess
import importlib
from pathlib import Path

from PHOEBUS.skills.registry import skill

CUSTOM_SKILLS_DIR = Path(__file__).parent / "custom"


@skill(
    "skill_create",
    risk="high",
    help_text="Crée un nouveau skill PHOEBUS de façon permanente en écrivant du code Python. UTILISE background=True si tu dois répondre à l'utilisateur pendant que le skill se crée en parallèle.",
    describe=lambda d: f"Apprentissage d'un nouveau skill : '{d.get('name', '?')}'",
)
async def skill_create(data: dict):
    """Crée un nouveau skill dynamiquement.
    
    Paramètres attendus dans `data` :
    - name: nom du fichier (sans .py) et nom de la fonction (ex: 'fetch_crypto')
    - help_text: description courte pour le LLM
    - code: le code Python complet de la fonction asynchrone décorée avec @skill
    """
    name = data.get("name", "").strip().lower()
    help_text = data.get("help_text", "").replace('"', "'")
    code = data.get("code", "").strip()
    background = data.get("background", False)
    
    if not name or not code:
        return "Il me faut un 'name' et le 'code' pour créer un skill."
        
    # Validation du nom
    if not name.isidentifier():
        return f"'{name}' n'est pas un nom de skill valide (lettres, chiffres, underscore uniquement)."
        
    # Sécurité basique
    if "import os" in code and "os.remove" in code:
        return "Opération dangereuse détectée dans le code."

    file_path = CUSTOM_SKILLS_DIR / f"{name}.py"
    
    # Injection du boilerplate si le code n'est pas complet
    if "@skill(" not in code:
        boilerplate = f'''from PHOEBUS.skills.registry import skill

@skill(
    "{name}",
    risk="medium",
    help_text="{help_text}",
    describe=lambda d: "{help_text}"
)
{code}
'''
        code = boilerplate

    async def _do_create():
        try:
            # Écriture du fichier
            file_path.write_text(code, encoding="utf-8")
            
            # Chargement dynamique
            module_name = f"PHOEBUS.skills.custom.{name}"
            importlib.import_module(module_name)
            
            # Notifier via websocket si en background
            if background:
                print(f"[DEVELOPER] Le skill '{name}' a fini de compiler en arrière-plan et est prêt.")
        except Exception as e:
            file_path.unlink(missing_ok=True)
            print(f"[DEVELOPER] Erreur création background pour '{name}': {e}")

    if background:
        import asyncio
        asyncio.create_task(_do_create())
        return f"Le processus d'apprentissage du skill '{name}' a été lancé en arrière-plan. Il sera bientôt disponible."
    
    # Mode synchrone
    try:
        await _do_create()
        return f"✅ Le skill '{name}' a été créé avec succès et est maintenant disponible !"
    except Exception as e:
        return f"Erreur lors de la création du skill : {e}"


@skill(
    "terminal_run",
    risk="high",
    help_text="Exécute une commande Bash dans le terminal du Mac (utile pour installer des packages pip, manipuler des fichiers, etc.)",
    describe=lambda d: f"Terminal : {d.get('command', '?')[:40]}",
)
async def terminal_run(data: dict):
    """Exécute une commande bash arbitraire sur l'hôte."""
    command = data.get("command", "").strip()
    if not command:
        return "Il me faut une commande bash à exécuter."
        
    try:
        import asyncio
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        
        out = stdout.decode('utf-8').strip()
        err = stderr.decode('utf-8').strip()
        
        res = []
        if out:
            res.append(f"STDOUT:\n```\n{out[:2000]}\n```")
        if err:
            res.append(f"STDERR:\n```\n{err[:1000]}\n```")
            
        if process.returncode == 0:
            return "\n".join(res) if res else "Commande exécutée avec succès (sans output)."
        else:
            return f"❌ Erreur (code {process.returncode}) :\n" + "\n".join(res)
    except Exception as e:
        return f"Erreur d'exécution du terminal : {e}"
