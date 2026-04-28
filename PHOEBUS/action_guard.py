# PHOEBUS/action_guard.py
"""Garde-fous anti-boucle pour les actions produites par l'IA.

Inspiré du pattern "loop guard" observé dans OpenJarvis, mais réduit au besoin
PHOEBUS : empêcher une réponse IA ou un plan de répéter la même action jusqu'à
créer des effets indésirables.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from dataclasses import dataclass
from typing import Any


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class ActionGuardConfig:
    enabled: bool = os.getenv("PHOEBUS_ACTION_GUARD", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    max_actions_per_batch: int = _int_env("PHOEBUS_ACTION_GUARD_MAX_ACTIONS", 8)
    max_identical_calls: int = _int_env("PHOEBUS_ACTION_GUARD_MAX_IDENTICAL", 2)
    ping_pong_window: int = _int_env("PHOEBUS_ACTION_GUARD_PINGPONG_WINDOW", 6)


@dataclass(slots=True)
class ActionGuardVerdict:
    blocked: bool = False
    reason: str = ""


class ActionSequenceGuard:
    """Surveille une séquence courte d'actions avant exécution."""

    def __init__(self, config: ActionGuardConfig | None = None):
        self.config = config or ActionGuardConfig()
        self._total = 0
        self._signatures: dict[str, int] = {}
        self._sign_sequence: deque[str] = deque(maxlen=max(2, self.config.ping_pong_window))

    def check(self, payload: dict[str, Any]) -> ActionGuardVerdict:
        if not self.config.enabled:
            return ActionGuardVerdict()

        self._total += 1
        action = str(payload.get("action") or "").strip() or "<sans_action>"

        if self._total > self.config.max_actions_per_batch:
            return ActionGuardVerdict(
                blocked=True,
                reason=(
                    f"trop d'actions dans la même séquence "
                    f"({self._total}>{self.config.max_actions_per_batch})"
                ),
            )

        signature = _signature(action, payload)
        self._signatures[signature] = self._signatures.get(signature, 0) + 1
        if self._signatures[signature] > self.config.max_identical_calls:
            return ActionGuardVerdict(
                blocked=True,
                reason=(
                    f"action répétée '{action}' "
                    f"({self._signatures[signature]} fois)"
                ),
            )

        self._sign_sequence.append(signature)
        if self._detect_ping_pong():
            return ActionGuardVerdict(
                blocked=True,
                reason="cycle répétitif d'actions détecté",
            )

        return ActionGuardVerdict()

    def _detect_ping_pong(self) -> bool:
        seq = list(self._sign_sequence)
        for period in (2, 3):
            if len(seq) < period * 2:
                continue
            tail = seq[-period * 2 :]
            pattern = tail[:period]
            if len(set(pattern)) > 1 and all(
                item == pattern[i % period] for i, item in enumerate(tail)
            ):
                return True
        return False


def _signature(action: str, payload: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        normalized = repr(payload)
    return hashlib.sha256(f"{action}:{normalized}".encode("utf-8")).hexdigest()[:16]
