# PHOEBUS/agent_runtime.py
"""Runtime léger pour agents PHOEBUS : max_turns, traces et statuts."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PHOEBUS.config import BASE_DIR


TRACE_FILE = BASE_DIR / "logs" / "agent_traces.jsonl"
_RECENT_RUNS: list[dict[str, Any]] = []


@dataclass(slots=True)
class AgentStepRecord:
    index: int
    action: str
    status: str
    reason: str = ""
    duration_ms: float = 0.0
    result: str = ""


@dataclass(slots=True)
class AgentRunTrace:
    run_id: str
    agent_type: str
    instruction: str
    status: str = "running"
    max_turns: int = 8
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    summary: str = ""
    steps: list[AgentStepRecord] = field(default_factory=list)

    def record_step(
        self,
        step: dict[str, Any],
        status: str,
        *,
        result: str = "",
        reason: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        self.steps.append(
            AgentStepRecord(
                index=int(step.get("step") or len(self.steps) + 1),
                action=str(step.get("action") or ""),
                status=status,
                reason=reason[:300],
                duration_ms=round(duration_ms, 1),
                result=(result or "")[:600],
            )
        )

    def finish(self, status: str, summary: str = "") -> dict[str, Any]:
        self.status = status
        self.summary = summary[:600]
        self.finished_at = time.time()
        data = self.to_dict()
        _remember_run(data)
        _append_jsonl(data)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_ms"] = round(((self.finished_at or time.time()) - self.started_at) * 1000, 1)
        return data


def start_agent_run(
    instruction: str,
    *,
    agent_type: str = "planner",
    max_turns: int = 8,
) -> AgentRunTrace:
    return AgentRunTrace(
        run_id=uuid.uuid4().hex[:12],
        agent_type=agent_type,
        instruction=instruction[:1000],
        max_turns=max_turns,
    )


def recent_agent_runs(limit: int = 5) -> list[dict[str, Any]]:
    if _RECENT_RUNS:
        return list(_RECENT_RUNS[-limit:])
    if not TRACE_FILE.exists():
        return []
    lines = TRACE_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    runs = []
    for line in lines:
        try:
            runs.append(json.loads(line))
        except Exception:
            continue
    return runs


def _remember_run(data: dict[str, Any]) -> None:
    _RECENT_RUNS.append(data)
    del _RECENT_RUNS[:-20]


def _append_jsonl(data: dict[str, Any]) -> None:
    try:
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[AGENT] trace non écrite : {exc}")
