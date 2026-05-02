"""Etat vocal runtime, expose sans secret par /diagnostics."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from math import sqrt
import os
import struct
import threading
from typing import Any

_LOCK = threading.Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=30)
_STATUS: dict[str, Any] = {
    "backend": None,
    "microphone": None,
    "available_microphones": [],
    "energy_threshold": None,
    "last_event": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_voice_event(event: str, **data: Any) -> None:
    payload = {"ts": _now(), "event": event, **data}
    with _LOCK:
        _EVENTS.append(payload)
        _STATUS["last_event"] = payload


def set_voice_status(**data: Any) -> None:
    with _LOCK:
        _STATUS.update(data)


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            **_STATUS,
            "events": list(_EVENTS),
        }


def audio_stats(audio_data: Any) -> dict[str, Any]:
    """Calcule des stats simples sans dépendre d'audioop, absent en Python 3.13."""
    try:
        raw = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        if not raw:
            return {"duration_ms": 0, "rms": 0, "peak": 0}

        sample_count = len(raw) // 2
        if sample_count <= 0:
            return {"duration_ms": 0, "rms": 0, "peak": 0}

        values = struct.unpack("<" + "h" * sample_count, raw)
        peak = max(abs(v) for v in values)
        rms = int(sqrt(sum(v * v for v in values) / sample_count))
        duration_ms = int(sample_count / 16000 * 1000)
        return {"duration_ms": duration_ms, "rms": rms, "peak": peak}
    except Exception:
        return {"duration_ms": None, "rms": None, "peak": None}


def microphone_config() -> dict[str, Any]:
    raw_index = os.getenv("PHOEBUS_MIC_DEVICE_INDEX", "").strip()
    index = None
    if raw_index:
        try:
            index = int(raw_index)
        except ValueError:
            index = None
    return {
        "device_index": index,
        "device_name": os.getenv("PHOEBUS_MIC_DEVICE_NAME", "").strip(),
        "energy_offset": _float_env("PHOEBUS_MIC_ENERGY_OFFSET", 50.0),
        "pause_threshold": _float_env("PHOEBUS_MIC_PAUSE_THRESHOLD", 0.65),
        "timeout": _float_env("PHOEBUS_MIC_TIMEOUT", 1.5),
        "phrase_time_limit": _float_env("PHOEBUS_MIC_PHRASE_TIME_LIMIT", 7.0),
    }


def microphone_inventory(sr_module: Any = None) -> dict[str, Any]:
    names: list[str] = []
    if sr_module is not None:
        try:
            names = list(sr_module.Microphone.list_microphone_names())
        except Exception:
            names = []

    default_input = None
    try:
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            idx = int(info.get("index"))
            default_input = {
                "index": idx,
                "name": str(info.get("name") or (names[idx] if 0 <= idx < len(names) else "")),
            }
        finally:
            pa.terminate()
    except Exception:
        default_input = None

    return {
        "names": names,
        "default_input": default_input,
    }


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
