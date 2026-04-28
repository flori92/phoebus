"""Dispatcher d'intention local — fast-path des commandes évidentes.

Objectif : court-circuiter l'appel LLM pour les commandes simples et répétitives
(allumer/éteindre une pièce, demander l'heure ou la date, ouvrir un dossier
connu, etc.). Latence : ~50 ms au lieu de ~1,2 s round-trip cloud.
"""
import re
import time
import json
from typing import Optional


# ── Normalisation ─────────────────────────────────────────────────────────

def _norm(texte: str) -> str:
    t = (texte or "").lower().strip()
    t = t.rstrip("?.!,;:")
    t = re.sub(r"\s+", " ", t)
    t = t.replace("s'il te plaît", "").replace("s'il te plait", "")
    t = t.replace("s'il vous plaît", "").replace("s'il vous plait", "")
    t = t.replace("stp", "").replace("svp", "").strip()
    return t


# ── Table des pièces reconnues ────────────────────────────────────────────
PIECES_ALIAS = {
    "salon": "salon", "sejour": "salon", "séjour": "salon", "living": "salon",
    "cuisine": "cuisine", "chambre": "chambre", "bureau": "bureau",
    "couloir": "couloir", "entree": "entree", "entrée": "entree",
    "salle de bain": "salle_de_bain", "sdb": "salle_de_bain",
    "toilettes": "toilettes", "wc": "toilettes", "garage": "garage",
    "cave": "cave", "terrasse": "terrasse", "jardin": "jardin",
}

_PIECE_PATTERN = "(?:" + "|".join(sorted(PIECES_ALIAS.keys(), key=len, reverse=True)) + ")"
_WAKE_PREFIX = r"(?:(?:phoebus|phébus|fébus|febus|feubus|rebus)[, ]*)?"


# ── Patterns ──────────────────────────────────────────────────────────────

_RE_ALLUME = re.compile(rf"^{_WAKE_PREFIX}(?:allume|éclaire|lumiere|lumière).+?(?P<piece>{_PIECE_PATTERN})$")
_RE_ETEINS = re.compile(rf"^{_WAKE_PREFIX}(?:éteins|eteins|coupe).+?(?P<piece>{_PIECE_PATTERN})$")
_RE_HEURE = re.compile(rf"^{_WAKE_PREFIX}(?:quelle heure est[- ]il|il est quelle heure|tu as l[' ]heure)$")
_RE_DATE = re.compile(rf"^{_WAKE_PREFIX}(?:quel jour (?:sommes|on est|est)|quelle (?:est la )?date)$")
_RE_METEO = re.compile(rf"^{_WAKE_PREFIX}(?:quel temps|quelle météo|la météo|le temps|il fait quoi).+?(?P<ville>[a-zà-ÿ' -]+)?$")
_RE_TIMER = re.compile(rf"^{_WAKE_PREFIX}(?:mets|lance|démarre|programme)?\s*(?:un\s+)?(?:minuteur|timer)\s*(?:de\s+)?(?P<n>\d+)\s*(?P<u>s|min|h)?(?:\s+pour\s+(?P<label>.+))?$")
_RE_SYS_STATS = re.compile(rf"^{_WAKE_PREFIX}(?:état du système|utilisation cpu|niveau de batterie)$")
_RE_SYS_CONTROL = re.compile(rf"^{_WAKE_PREFIX}(?P<type>verrouille|veille|coupe le son|remets le son|capture|corbeille)")

class IntentResult:
    __slots__ = ("name", "reply", "confidence")
    def __init__(self, name: str, reply: str, confidence: float = 1.0):
        self.name = name
        self.reply = reply
        self.confidence = confidence

def _unite_to_seconds(n: int, unit: str) -> int:
    u = (unit or "min").lower()
    if u.startswith("s"): return n
    if u.startswith("h"): return n * 3600
    return n * 60

def detect(texte: str) -> Optional[IntentResult]:
    """Tente une reconnaissance locale. Renvoie None si incertain."""
    if not texte: return None
    t = _norm(texte)
    if not t: return None

    # --- Domotique ---
    m = _RE_ALLUME.match(t)
    if m:
        p = PIECES_ALIAS.get(m.group("piece"))
        return IntentResult("allume", json.dumps({"action": "ha_lumiere", "piece": p, "etat": "on"}))
    
    m = _RE_ETEINS.match(t)
    if m:
        p = PIECES_ALIAS.get(m.group("piece"))
        return IntentResult("eteins", json.dumps({"action": "ha_lumiere", "piece": p, "etat": "off"}))

    # --- Heure / Date ---
    if _RE_HEURE.match(t):
        return IntentResult("heure", f"Il est {time.strftime('%Hh%M')}, Monsieur.")
    if _RE_DATE.match(t):
        return IntentResult("date", f"Nous sommes le {time.strftime('%A %d %B %Y')}.")

    # --- Météo ---
    m = _RE_METEO.match(t)
    if m:
        v = (m.group("ville") or "").strip()
        return IntentResult("meteo", json.dumps({"action": "meteo", "ville": v} if v else {"action": "meteo"}))

    # --- Timers ---
    m = _RE_TIMER.match(t)
    if m:
        n = int(m.group("n"))
        sec = _unite_to_seconds(n, m.group("u"))
        return IntentResult("timer", json.dumps({"action": "timer", "minutes": sec//60, "secondes": sec%60, "label": m.group("label") or "minuteur"}))

    # --- Système ---
    if _RE_SYS_STATS.match(t):
        return IntentResult("system_stats", json.dumps({"action": "system_stats"}))
    
    m = _RE_SYS_CONTROL.match(t)
    if m:
        cmd = m.group("type")
        map_cmd = {"verrouille": "lock", "veille": "sleep", "coupe le son": "mute", "remets le son": "unmute", "capture": "screenshot", "corbeille": "empty_trash"}
        return IntentResult("sys_control", json.dumps({"action": "system_control", "type": map_cmd.get(cmd)}))

    return None
