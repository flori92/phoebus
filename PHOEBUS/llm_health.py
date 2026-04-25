"""Circuit breaker par provider LLM.

Problème observé : quand Gemini est en `429 RESOURCE_EXHAUSTED` (quota
free tier dépassé), on le réessaie à chaque tour en loggant 3 Ko de
JSON d'erreur. C'est coûteux (latence, bande passante) et ça pollue les
logs.

Solution : on retient la dernière panne par provider avec un backoff
suggéré (souvent fourni par l'API dans `retryDelay`), et on skip
silencieusement le provider tant qu'on est dans la fenêtre d'exclusion.

Usage :

    from PHOEBUS.llm_health import skip, record_failure, record_success

    if skip("gemini"):
        # on ne tente même pas l'appel
        ...
    try:
        rep = await call_gemini()
        record_success("gemini")
    except Exception as e:
        record_failure("gemini", e)
        raise
"""
import re
import time
from typing import Optional


# Durée par défaut d'exclusion après un échec (en secondes).
DEFAULT_BACKOFF_S = 60
# Pour les 429 avec retryDelay explicite, on le respecte (plafonné).
MAX_BACKOFF_S = 600

# État interne : {"gemini": {"until": ts, "reason": "..."}}
_state: dict = {}

_RE_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def _parse_retry_delay(msg: str) -> Optional[float]:
    """Extrait retryDelay='Xs' d'un message d'erreur Google API."""
    m = _RE_RETRY_DELAY.search(msg or "")
    if not m:
        return None
    try:
        return min(MAX_BACKOFF_S, float(m.group(1)))
    except Exception:
        return None


def record_failure(provider: str, exc: Exception) -> None:
    """Enregistre un échec. Calcule une fenêtre d'exclusion intelligente
    selon la nature de l'erreur."""
    msg = str(exc)
    backoff = DEFAULT_BACKOFF_S

    retry_delay = _parse_retry_delay(msg)
    if retry_delay is not None:
        backoff = retry_delay + 2  # marge

    # 429 quota quotidien → on skip pour longtemps (1h).
    if "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        # Si on a un retryDelay explicite, on s'y fie, sinon 5 min.
        if retry_delay is None:
            backoff = 300

    _state[provider] = {
        "until": time.time() + backoff,
        "reason": _short_reason(msg),
    }


def record_success(provider: str) -> None:
    _state.pop(provider, None)


def skip(provider: str) -> bool:
    """Vrai si on doit skipper ce provider pour ne pas retaper sur 429."""
    entry = _state.get(provider)
    if not entry:
        return False
    if time.time() >= entry["until"]:
        _state.pop(provider, None)
        return False
    return True


def status() -> dict:
    """Renvoie un snapshot lisible de l'état des providers."""
    now = time.time()
    out = {}
    for prov, entry in list(_state.items()):
        remaining = max(0, int(entry["until"] - now))
        if remaining == 0:
            _state.pop(prov, None)
            continue
        out[prov] = {"remaining_s": remaining, "reason": entry["reason"]}
    return out


def _short_reason(msg: str) -> str:
    """Condense un message d'erreur API verbeux en une ligne."""
    if not msg:
        return "erreur"
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return "quota 429"
    if "500" in msg or "503" in msg:
        return "serveur indispo (5xx)"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "timeout"
    if "deadline" in msg.lower():
        return "deadline"
    # On prend juste la première ligne et on tronque.
    first_line = msg.strip().split("\n", 1)[0]
    return first_line[:80]
