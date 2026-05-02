import functools
from types import SimpleNamespace
from typing import Callable, Dict, Any, Optional

SKILL_REGISTRY: Dict[str, dict] = {}
RISK_ORDER = ("high", "medium", "low")


def skill(
    name: str,
    risk: str = "low",
    help_text: str = "",
    describe: Optional[Callable[[Dict[str, Any]], str]] = None,
    **legacy_kwargs,
):
    """
    Décorateur pour enregistrer une action comme un Skill modulaire.
    - risk: 'low' (exécution libre), 'medium' (avertissement), 'high' (confirmation stricte)
    - help_text: Description pour les logs ou pour l'IA
    - describe: Fonction qui retourne une phrase explicative de l'action en cours (ex: "J'allume le salon")
    """
    if not help_text and "help" in legacy_kwargs:
        help_text = str(legacy_kwargs["help"] or "")

    def decorator(func: Callable):
        SKILL_REGISTRY[name] = {
            "func": func,
            "risk": risk,
            "help": help_text,
            "describe": describe or (lambda d: f"Exécuter {name}"),
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


def get_skill(action_name: str):
    """Retourne les métadonnées d'un skill avec l'ancienne API attributaire."""
    meta = SKILL_REGISTRY.get(action_name)
    if meta is None:
        return None
    return SimpleNamespace(
        name=action_name,
        func=meta.get("func"),
        risk=meta.get("risk", "low"),
        help=meta.get("help", ""),
        describe=meta.get("describe"),
    )


def list_skills() -> list[str]:
    return sorted(SKILL_REGISTRY)


def risk_of(action_name: str, fallback: str = "low") -> str:
    """Retourne le niveau de risque d'un skill (low, medium, high)."""
    if action_name in SKILL_REGISTRY:
        return SKILL_REGISTRY[action_name].get("risk", fallback)
    return fallback


def capability_manifest(max_items: int | None = None) -> str:
    """Retourne un manifeste compact des skills réellement enregistrés.

    Le prompt IA doit refléter les capacités exécutables, pas une liste
    historique maintenue à la main. Ce manifeste reste volontairement textuel:
    les arguments détaillés sont donnés par les règles spécialisées du prompt,
    tandis que cette section sert de source de vérité pour les noms d'actions
    et leur niveau de risque.
    """
    if not SKILL_REGISTRY:
        return ""

    grouped: dict[str, list[tuple[str, str]]] = {risk: [] for risk in RISK_ORDER}
    grouped["other"] = []
    for name, meta in sorted(SKILL_REGISTRY.items()):
        risk = str(meta.get("risk") or "low").lower()
        bucket = risk if risk in grouped else "other"
        help_text = str(meta.get("help") or "").strip()
        grouped[bucket].append((name, help_text))

    lines = [
        "CAPACITES ENREGISTREES (source de verite):",
        'Pour utiliser une capacite, reponds avec un JSON strict: {"action": "nom_action", ...}.',
        "Respecte le niveau de risque: high = confirmation obligatoire, medium = annonce avant execution, low = execution directe.",
    ]
    emitted = 0
    labels = {
        "high": "Risque high",
        "medium": "Risque medium",
        "low": "Risque low",
        "other": "Risque non classe",
    }
    for risk in (*RISK_ORDER, "other"):
        entries = grouped.get(risk) or []
        if not entries:
            continue
        lines.append(f"{labels[risk]}:")
        for name, help_text in entries:
            if max_items is not None and emitted >= max_items:
                lines.append("- ...")
                return "\n".join(lines)
            suffix = f" - {help_text}" if help_text else ""
            lines.append(f"- {name}{suffix}")
            emitted += 1
    return "\n".join(lines)
