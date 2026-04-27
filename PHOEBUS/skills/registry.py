import functools
from typing import Callable, Dict, Any, Optional

SKILL_REGISTRY: Dict[str, dict] = {}

def skill(
    name: str,
    risk: str = "low",
    help_text: str = "",
    describe: Optional[Callable[[Dict[str, Any]], str]] = None
):
    """
    Décorateur pour enregistrer une action comme un Skill modulaire.
    - risk: 'low' (exécution libre), 'medium' (avertissement), 'high' (confirmation stricte)
    - help_text: Description pour les logs ou pour l'IA
    - describe: Fonction qui retourne une phrase explicative de l'action en cours (ex: "J'allume le salon")
    """
    def decorator(func: Callable):
        SKILL_REGISTRY[name] = {
            "func": func,
            "risk": risk,
            "help": help_text,
            "describe": describe or (lambda d: f"Exécuter {name}")
        }
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator

async def execute_skill(action_name: str, data: dict) -> tuple[bool, str]:
    """Exécute un skill sécurisé, ou échoue si inconnu."""
    if action_name not in SKILL_REGISTRY:
        return False, "Action inconnue."
    
    skill_meta = SKILL_REGISTRY[action_name]
    
    try:
        # Ici on pourra brancher la confirmation si risk == 'high'
        result = await skill_meta["func"](data)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return True, result or "Action effectuée."
    except Exception as e:
        print(f"[SKILL ERROR] {action_name} : {e}")
        return False, f"Erreur lors de l'exécution de {action_name}."

def describe_skill(action_name: str, data: dict) -> str:
    """Retourne une description vocale amicale de l'action."""
    if action_name not in SKILL_REGISTRY:
        return "Je m'occupe de cela."
    return SKILL_REGISTRY[action_name]["describe"](data)

def is_skill_registered(action_name: str) -> bool:
    return action_name in SKILL_REGISTRY

def risk_of(action_name: str, fallback: str = "low") -> str:
    """Retourne le niveau de risque d'un skill (low, medium, high)."""
    if action_name in SKILL_REGISTRY:
        return SKILL_REGISTRY[action_name].get("risk", fallback)
    return fallback
