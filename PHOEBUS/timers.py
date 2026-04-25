"""Timers et rappels persistants.

Deux usages :
- **timer** : minuteur court (< 1 h typiquement) — "mets un minuteur de
  5 minutes pour les pâtes".
- **rappel** : message à délivrer plus tard — "rappelle-moi d'appeler
  maman dans 2 heures".

Les deux partagent la même structure (date d'expiration absolue + label)
et sont stockés dans `jarvis_timers.json` pour survivre aux redémarrages.
Un dispatcher asyncio vérifie toutes les 2 s si un timer doit s'exécuter
et appelle le callback `parler()` avec un message contextuel.

API publique :
    set_timer(duration_s, label, kind="timer")  -> id (int)
    list_timers()                               -> liste triée par échéance
    cancel_timer(id)                            -> bool
    loop_tick(parler)                           -> coroutine pour le scheduler
"""
import json
import time
from pathlib import Path
from typing import List, Optional

from PHOEBUS.config import BASE_DIR


TIMERS_FILE = BASE_DIR / "jarvis_timers.json"


def _load() -> dict:
    try:
        if TIMERS_FILE.exists():
            with open(TIMERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[TIMERS] chargement : {e}")
    return {"next_id": 1, "timers": []}


def _save(data: dict) -> None:
    try:
        with open(TIMERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TIMERS] sauvegarde : {e}")


def set_timer(duration_s: float, label: str = "", kind: str = "timer") -> int:
    """Programme un timer. Renvoie son ID pour annulation éventuelle."""
    duration_s = max(1.0, float(duration_s))
    data = _load()
    tid = int(data["next_id"])
    data["next_id"] = tid + 1
    data["timers"].append({
        "id": tid,
        "kind": kind,  # "timer" | "rappel"
        "label": (label or "").strip(),
        "due_ts": time.time() + duration_s,
        "created_ts": time.time(),
    })
    _save(data)
    return tid


def list_timers() -> List[dict]:
    data = _load()
    items = list(data.get("timers", []))
    items.sort(key=lambda t: t.get("due_ts", 0))
    return items


def cancel_timer(tid: int) -> bool:
    data = _load()
    original = len(data.get("timers", []))
    data["timers"] = [t for t in data["timers"] if t.get("id") != tid]
    if len(data["timers"]) < original:
        _save(data)
        return True
    return False


def clear_expired() -> int:
    """Supprime les timers échus (appelé après annonce)."""
    data = _load()
    now = time.time()
    kept = [t for t in data["timers"] if t.get("due_ts", 0) > now]
    removed = len(data["timers"]) - len(kept)
    if removed:
        data["timers"] = kept
        _save(data)
    return removed


async def tick(parler) -> None:
    """À appeler périodiquement (toutes les 2-5 s) depuis le scheduler
    proactif. Prononce les timers échus puis les retire du stockage.

    `parler` est une coroutine : la même que `voice.parler`.
    """
    now = time.time()
    data = _load()
    changed = False
    for t in list(data.get("timers", [])):
        if t.get("due_ts", 0) <= now:
            kind = t.get("kind", "timer")
            label = t.get("label") or ""
            if kind == "rappel":
                msg = f"Rappel, Monsieur : {label}." if label else "Rappel programmé, Monsieur."
            else:
                msg = f"Votre minuteur est terminé : {label}." if label else "Minuteur terminé, Monsieur."
            try:
                await parler(msg)
            except Exception as e:
                print(f"[TIMERS] parler : {e}")
            data["timers"].remove(t)
            changed = True
    if changed:
        _save(data)


def format_duration(seconds: float) -> str:
    """Formate une durée en français court. Ex: 90 → '1 min 30 s'."""
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d}"
