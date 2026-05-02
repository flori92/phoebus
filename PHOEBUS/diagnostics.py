"""Diagnostics publics sans secrets pour surveiller PHOEBUS."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import PHOEBUS.state as state
from PHOEBUS.config import BASE_DIR, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from PHOEBUS.llm_health import status as llm_status
from PHOEBUS.observability import request_snapshot, snapshot as phase_snapshot, trace_snapshot
from PHOEBUS.brain_router import available_provider_names
from PHOEBUS.response_cache import status as tts_cache_status
from PHOEBUS.runtime_resources import runtime_snapshot
from PHOEBUS.stt_backends import stt_status
from PHOEBUS.voice_diagnostics import snapshot as voice_snapshot


def _port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def diagnostics_snapshot() -> dict:
    ai_metrics = _json_file(BASE_DIR / "logs" / "ai_router_metrics.json")
    active_provider_names = set(available_provider_names())
    providers = {}
    for name, item in ai_metrics.items():
        if name not in active_provider_names:
            continue
        calls = int(item.get("calls", 0) or 0)
        success = int(item.get("success", 0) or 0)
        failures = int(item.get("failure", 0) or 0)
        providers[name] = {
            "calls": calls,
            "success": success,
            "failure": failures,
            "success_rate": round(success / calls, 3) if calls else None,
            "avg_latency_ms": item.get("avg_latency_ms"),
            "cooldown_until": item.get("cooldown_until", 0),
            "failures_streak": item.get("failures_streak", 0),
        }

    try:
        from PHOEBUS.skills import list_skills

        skills = list_skills()
    except Exception:
        skills = []

    return {
        "ts": time.time(),
        "runtime": {
            "resources": runtime_snapshot(),
            "ports": {
                "mobile_http_8090": True,
                "websocket_8765": True,
                "frontend_8080": _port_open("127.0.0.1", 8080),
            },
            "state": {
                "is_speaking": state.is_speaking,
                "is_thinking": state.is_thinking,
                "conversation": state.is_in_conversation(),
                "post_speak_cooldown": state.in_post_speak_cooldown(),
                "connected_clients": len(state.CONNECTED_CLIENTS),
                "background_tasks": len(state.active_background_tasks()),
            },
        },
        "channels": {
            "telegram": {
                "configured": bool(TELEGRAM_TOKEN),
                "restricted_chat": bool(TELEGRAM_CHAT_ID),
            },
            "websocket_auth": _websocket_auth_status(),
        },
        "skills": {
            "count": len(skills),
            "names": skills,
        },
        "llm": {
            "cooldowns": llm_status(),
            "providers": providers,
        },
        "observability": {
            "requests": request_snapshot(),
            "phases": phase_snapshot(),
            "traces": trace_snapshot(),
        },
        "voice": {
            **voice_snapshot(),
            "stt": stt_status(),
            "tts_cache": tts_cache_status(),
        },
    }


def _websocket_auth_status() -> dict:
    try:
        from PHOEBUS.ws_pairing import pairing_status

        return pairing_status()
    except Exception:
        return {"enabled": False, "paired_devices": 0}
