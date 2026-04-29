"""Pairing local WebSocket sans token dans l'URL."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from PHOEBUS.config import BASE_DIR

PAIRINGS_FILE = Path(os.getenv("PHOEBUS_WS_PAIRINGS_FILE", BASE_DIR / "logs" / "ws_pairings.json"))
PAIRING_ENABLED = os.getenv("PHOEBUS_WS_PAIRING_REQUIRED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AUTO_ENROLL_LOCAL = os.getenv("PHOEBUS_WS_PAIRING_AUTO_ENROLL", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _load() -> dict[str, Any]:
    try:
        if PAIRINGS_FILE.exists():
            data = json.loads(PAIRINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"devices": {}}


def _save(data: dict[str, Any]) -> None:
    PAIRINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PAIRINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PAIRINGS_FILE)


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _is_local_network(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def pairing_status() -> dict[str, Any]:
    data = _load()
    return {
        "enabled": PAIRING_ENABLED,
        "auto_enroll_local": AUTO_ENROLL_LOCAL,
        "paired_devices": len(data.get("devices", {}) or {}),
        "file": str(PAIRINGS_FILE),
    }


def validate_pairing(device_id: str | None, secret: str | None) -> bool:
    if not PAIRING_ENABLED:
        return True
    if not device_id or not secret:
        return False
    data = _load()
    item = (data.get("devices") or {}).get(device_id)
    if not item:
        return False
    return hmac.compare_digest(str(item.get("secret_hash", "")), _hash_secret(secret))


def enroll_pairing(*, client_ip: str, client_type: str, client_name: str) -> dict[str, str] | None:
    if not PAIRING_ENABLED or not AUTO_ENROLL_LOCAL or not _is_local_network(client_ip):
        return None
    data = _load()
    devices = data.setdefault("devices", {})
    device_id = f"dev_{secrets.token_hex(8)}"
    secret = secrets.token_urlsafe(32)
    devices[device_id] = {
        "secret_hash": _hash_secret(secret),
        "client_type": client_type or "unknown",
        "client_name": (client_name or "")[:160],
        "first_ip": client_ip,
        "created_ts": time.time(),
        "last_seen_ts": time.time(),
    }
    _save(data)
    return {"device_id": device_id, "secret": secret}


def mark_seen(device_id: str | None, client_ip: str) -> None:
    if not device_id:
        return
    data = _load()
    item = (data.get("devices") or {}).get(device_id)
    if not item:
        return
    item["last_ip"] = client_ip
    item["last_seen_ts"] = time.time()
    _save(data)
