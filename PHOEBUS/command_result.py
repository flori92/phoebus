"""Contrat de résultat commun pour tous les adaptateurs PHOEBUS."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from uuid import uuid4
from typing import Any


def new_trace_id() -> str:
    return f"cmd_{uuid4().hex[:16]}"


@dataclass(slots=True)
class CommandResult:
    """Résultat structuré d'une commande, indépendant du canal d'entrée."""

    text: str = ""
    source: str = "unknown"
    trace_id: str = field(default_factory=new_trace_id)
    ok: bool = True
    status: str = "ok"
    route: str = "command"
    speech_text: str | None = None
    confirmation_required: bool = False
    pending_action: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    action_messages: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    created_ts: float = field(default_factory=time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def reply_text(self, fallback: str = "") -> str:
        return self.text or self.speech_text or fallback

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "source": self.source,
            "ok": self.ok,
            "status": self.status,
            "route": self.route,
            "reply": self.reply_text(),
            "confirmation_required": self.confirmation_required,
            "duration_ms": round(self.duration_ms, 1),
        }
        if self.action_messages:
            payload["action_messages"] = list(self.action_messages)
        if self.pending_action:
            payload["pending_action"] = {
                key: value
                for key, value in self.pending_action.items()
                if key not in {"body", "content", "token", "audio_b64"}
            }
        return payload
