"""Conscience contextuelle de PHOEBUS — la vraie proactivité.

Aujourd'hui PHOEBUS attend qu'on lui parle. Ce module croise plusieurs
signaux à intervalle régulier pour produire des observations utiles SANS
qu'on lui demande :

- Calendrier Google : prochain événement, retard probable, notes liées
- Météo : changement de temps qui demande un ajustement (parapluie, lumières)
- État machine : batterie faible, disque plein, mises à jour
- Activité utilisateur : silence prolongé, retour après absence
- RSS : alertes critiques (météo, transport)

Chaque "observation" est une dataclass standardisée qui peut être :
- prononcée immédiatement (urgence)
- mise en file pour un briefing (information utile mais non urgente)
- ignorée si déjà annoncée récemment (dedup)

L'awareness loop tourne dans la boucle `proactive` existante (rules
décorées). On ajoute donc des @rule à proactive.py qui appellent les
checks d'awareness.
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ── Configuration ───────────────────────────────────────────────────────

# Délai mini entre 2 annonces du même type (anti-spam)
DEDUP_WINDOW_S = 1800  # 30 min

# Activation par défaut
AWARENESS_ENABLED = os.getenv("PHOEBUS_AWARENESS", "1").strip() in ("1", "true", "yes")

# Heure (du calendrier) à laquelle PHOEBUS prévient avant un meeting
MEETING_WARN_MINUTES = int(os.getenv("PHOEBUS_MEETING_WARN_MIN", "10"))

# Pluie : seuil à partir duquel on suggère un parapluie (mm/h)
RAIN_THRESHOLD_MMH = float(os.getenv("PHOEBUS_RAIN_THRESHOLD", "1.5"))


# ── Observations ─────────────────────────────────────────────────────────

@dataclass
class Observation:
    """Une chose que PHOEBUS a remarquée et veut peut-être partager."""
    kind: str           # "meeting" | "weather" | "battery" | "disk" | "silence_back" | "alert"
    message: str        # Texte parlable
    urgency: str = "info"   # "urgent" | "info" | "ambient"
    ts: float = field(default_factory=time.time)


# Historique des observations annoncées (dedup).
_announced: dict = {}  # {key: timestamp}


def _already_said(key: str) -> bool:
    """Vrai si la même observation a été annoncée dans la fenêtre de dedup."""
    last = _announced.get(key, 0)
    return (time.time() - last) < DEDUP_WINDOW_S


def _mark_said(key: str) -> None:
    _announced[key] = time.time()


# ── Source : Calendrier ──────────────────────────────────────────────────

async def check_meetings() -> List[Observation]:
    """Vérifie le prochain événement Google Calendar.

    Si on est à moins de MEETING_WARN_MINUTES → urgence.
    Si on est au moment exact (à 30s près) → urgent + tente de récupérer
    les notes Google Doc associées.
    """
    if not AWARENESS_ENABLED:
        return []
    try:
        from PHOEBUS.google_services import lister_evenements_calendar
    except Exception:
        return []

    try:
        raw = await asyncio.to_thread(lister_evenements_calendar)
    except Exception:
        return []
    if not raw or "non disponible" in raw.lower():
        return []

    # Format renvoyé : "2025-04-26T14:00:00+02:00 : Réunion équipe\n..."
    obs: List[Observation] = []
    now = time.time()
    import datetime as _dt
    for line in raw.splitlines():
        if " : " not in line:
            continue
        when_str, _, summary = line.partition(" : ")
        try:
            # parse ISO 8601 (avec ou sans timezone)
            when = _dt.datetime.fromisoformat(when_str.strip())
        except Exception:
            continue
        delta_s = when.timestamp() - now
        if delta_s < 0:
            continue  # déjà passé
        # Fenêtre de pré-annonce
        warn_window = MEETING_WARN_MINUTES * 60
        if delta_s <= warn_window:
            mins = max(1, int(delta_s // 60))
            key = f"meeting:{summary[:40]}"
            if _already_said(key):
                continue
            _mark_said(key)
            obs.append(
                Observation(
                    kind="meeting",
                    message=f"Floriace, dans {mins} minutes : {summary.strip()}.",
                    urgency="urgent" if delta_s < 180 else "info",
                )
            )
            break  # on n'annonce que le prochain
    return obs


# ── Source : Météo ───────────────────────────────────────────────────────────

async def check_weather() -> List[Observation]:
    """Si la pluie arrive et qu'il y a un événement extérieur prévu, prévient."""
    if not AWARENESS_ENABLED:
        return []
    try:
        from PHOEBUS.home import get_alertes_meteo
    except Exception:
        return []

    try:
        alerte = await asyncio.to_thread(get_alertes_meteo)
    except Exception:
        return []
    if not alerte or "pas d'alerte" in alerte.lower():
        return []

    key = f"weather:{alerte[:80]}"
    if _already_said(key):
        return []
    _mark_said(key)
    return [Observation(kind="weather", message=alerte, urgency="info")]


# ── Source : État machine (batterie + disque, macOS prio) ──────────────────────

async def check_machine() -> List[Observation]:
    """Surveille batterie et disque local."""
    if not AWARENESS_ENABLED:
        return []
    obs: List[Observation] = []

    # Batterie macOS via pmset
    try:
        proc = await asyncio.create_subprocess_exec(
            "pmset", "-g", "batt",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        text = (out or b"").decode("utf-8", errors="replace")
        # Parse "78%; discharging"
        import re
        m = re.search(r"(\d+)%;\s*(\w+)", text)
        if m:
            pct = int(m.group(1))
            state_pmset = m.group(2)
            if pct <= 15 and "discharging" in state_pmset:
                key = f"battery:{pct // 5}"
                if not _already_said(key):
                    _mark_said(key)
                    obs.append(Observation(
                        kind="battery",
                        message=f"Batterie à {pct} %, je conseille de brancher le Mac.",
                        urgency="urgent" if pct <= 8 else "info",
                    ))
    except Exception:
        pass

    # Espace disque local (chemin home)
    try:
        import shutil
        usage = shutil.disk_usage(os.path.expanduser("~"))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 5:
            key = f"disk:{int(free_gb)}"
            if not _already_said(key):
                _mark_said(key)
                obs.append(Observation(
                    kind="disk",
                    message=f"Il ne reste que {free_gb:.1f} Go sur le disque, vous voudrez peut-être faire le ménage.",
                    urgency="info",
                ))
    except Exception:
        pass

    return obs


# ── Source : Retour après silence prolongé ──────────────────────────────────

async def check_user_return() -> List[Observation]:
    """Si l'utilisateur a été silencieux >2h et revient (activité récente),
    on dit bonjour de nouveau."""
    if not AWARENESS_ENABLED:
        return []
    try:
        import PHOEBUS.state as state
    except Exception:
        return []
    secs_idle = state.seconds_since_user_activity() if hasattr(state, "seconds_since_user_activity") else None
    if secs_idle is None:
        return []
    # Pas une vraie obs détectable ici (on n'a pas l'info du retour) — on
    # laisse cette branche vide pour l'instant. Hook prêt si un jour on
    # capte des signaux clavier/souris.
    return []


# ── Boucle principale ─────────────────────────────────────────────────────

CHECKS: List[Callable] = [
    check_meetings,
    check_weather,
    check_machine,
    check_user_return,
]


async def collect() -> List[Observation]:
    """Lance tous les checks en parallèle. Renvoie les observations."""
    if not AWARENESS_ENABLED:
        return []
    results = await asyncio.gather(
        *[c() for c in CHECKS], return_exceptions=True
    )
    obs: List[Observation] = []
    for r in results:
        if isinstance(r, list):
            obs.extend(r)
    # Tri : urgent d'abord
    rank = {"urgent": 0, "info": 1, "ambient": 2}
    obs.sort(key=lambda o: rank.get(o.urgency, 3))
    return obs


async def announce_due(parler_fn) -> int:
    """Appelée par la boucle proactive. Annonce les observations urgentes
    et stocke les autres pour un éventuel briefing.
    Renvoie le nombre d'observations annoncées vocalement."""
    obs = await collect()
    spoken = 0
    for o in obs:
        if o.urgency == "urgent":
            try:
                await parler_fn(o.message)
                spoken += 1
            except Exception:
                pass
        elif o.urgency == "info":
            # On ne spamme pas la voix : seulement si pas en conversation.
            try:
                import PHOEBUS.state as state
                if state.is_in_conversation() or state.is_speaking:
                    continue
                await parler_fn(o.message)
                spoken += 1
            except Exception:
                pass
    return spoken


# ── Mode privacy ─────────────────────────────────────────────────────────────

# Quand actif, l'awareness loop s'éteint complètement.
# Activable via skill ou directement par variable.
_privacy_until_ts = 0.0


def enable_privacy(duration_minutes: float = 60.0) -> None:
    global _privacy_until_ts
    _privacy_until_ts = time.time() + duration_minutes * 60


def disable_privacy() -> None:
    global _privacy_until_ts
    _privacy_until_ts = 0.0


def in_privacy() -> bool:
    return time.time() < _privacy_until_ts
