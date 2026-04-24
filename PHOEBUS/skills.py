"""Registre de compétences (skills) de PHOEBUS.

Au lieu d'alimenter le grand `elif` de `actions.py`, un skill se déclare
via le décorateur `@skill(...)` et devient automatiquement dispatché.

Chaque skill porte :
- `name` : nom d'action renvoyé par le modèle dans son JSON (ex: "meteo").
- `handler` : coroutine `async def fn(data: dict) -> None` (elle parle toute seule).
- `risk` : "low" | "medium" | "high" — contrôle la politique de confirmation.
- `describe` : `fn(data) -> str` humainement compréhensible (pour le prompt de confirmation).
- `background` : True si l'action doit tourner en tâche de fond (non bloquante).

L'ancien dispatcher d'`actions.py` reste en place et sert de fallback ; les
actions peuvent être migrées progressivement.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


RISK_LEVELS = ("low", "medium", "high")


@dataclass
class Skill:
    name: str
    handler: Callable[[Dict[str, Any]], Awaitable[None]]
    risk: str = "low"
    describe: Optional[Callable[[Dict[str, Any]], str]] = None
    help: str = ""
    background: bool = False


_REGISTRY: Dict[str, Skill] = {}


def skill(name, risk="low", describe=None, help="", background=False):
    """Décorateur d'enregistrement d'un skill."""
    if risk not in RISK_LEVELS:
        raise ValueError(f"risk doit être parmi {RISK_LEVELS}")

    def deco(fn):
        _REGISTRY[name] = Skill(
            name=name,
            handler=fn,
            risk=risk,
            describe=describe,
            help=help,
            background=background,
        )
        return fn

    return deco


def get_skill(name) -> Optional[Skill]:
    return _REGISTRY.get(name)


def list_skills() -> Dict[str, Skill]:
    return dict(_REGISTRY)


def risk_of(action: str, fallback: str = "low") -> str:
    sk = _REGISTRY.get(action)
    return sk.risk if sk else fallback


def describe_skill(data: Dict[str, Any]) -> Optional[str]:
    sk = _REGISTRY.get(data.get("action", ""))
    if sk and sk.describe:
        try:
            return sk.describe(data)
        except Exception:
            return None
    return None
