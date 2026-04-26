"""Routeur de cerveau IA pour PHOEBUS.

Ce module ne parle a aucun fournisseur directement. Il decide quel cerveau
essayer, dans quel ordre, et garde une petite memoire operationnelle des
latences/echecs pour eviter de retenter betement un service degrade.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from PHOEBUS.config import BASE_DIR


PROVIDERS = ("gemini", "groq", "arena", "openai", "mistral", "kimi", "grok", "ollama")
DEFAULT_ORDER = ("gemini", "groq", "arena", "openai", "mistral", "kimi", "grok", "ollama")
METRICS_FILE = BASE_DIR / "logs" / "ai_router_metrics.json"
FAIL_COOLDOWN_SECONDS = 45
QUOTA_COOLDOWN_SECONDS = 3600  # 1 heure pour les erreurs de quota (429)


@dataclass(frozen=True)
class BrainProfile:
    """Profil minimal d'une requete pour router intelligemment."""

    kind: str
    priority: str
    preferred_provider: Optional[str] = None
    needs_realtime: bool = False
    complexity: int = 1
    timeout_s: float = 8.0


def _csv(value: str, fallback: Iterable[str]) -> list[str]:
    items = [x.strip().lower() for x in (value or "").split(",") if x.strip()]
    valid = [x for x in items if x in PROVIDERS]
    return valid or list(fallback)


def configured_order() -> list[str]:
    return _csv(os.getenv("PHOEBUS_BRAIN_ORDER", ""), DEFAULT_ORDER)


def configured_mode() -> str:
    mode = os.getenv("PHOEBUS_BRAIN_MODE", "balanced").strip().lower()
    return mode if mode in {"balanced", "speed", "smart", "privacy"} else "balanced"


def build_profile(texte: str, streaming: bool = False, in_conversation: bool = False) -> BrainProfile:
    """Classe une requete sans appel reseau.

    Le but est conservateur : accelerer les cas simples, garder Gemini en
    principal pour les taches complexes/multimodales, et router les sujets X
    vers Grok quand il est disponible.
    """
    t = (texte or "").lower().strip()
    words = t.split()
    word_count = len(words)

    realtime_markers = (
        "aujourd'hui", "maintenant", "actuel", "actuelle", "dernier",
        "derniere", "dernière", "news", "actualité", "actualite",
        "score", "resultat", "résultat", "classement", "bourse",
        "prix", "meteo", "météo",
    )
    x_markers = ("sur x", "twitter", "x.com", "grok", "elon")
    command_markers = (
        "allume", "eteins", "éteins", "ouvre", "lance", "active",
        "désactive", "desactive", "mets", "règle", "regle",
    )
    deep_markers = (
        "analyse", "architecture", "strategie", "stratégie", "compare",
        "explique", "plan", "conçois", "concois", "optimise", "ameliore",
        "améliore", "diagnostic", "securite", "sécurité",
    )

    needs_realtime = any(m in t for m in realtime_markers)
    preferred = "grok" if any(m in t for m in x_markers) else None

    if any(m in t for m in command_markers):
        kind = "command"
    elif needs_realtime:
        kind = "realtime"
        # L'Arène est excellente pour le temps réel via Claude 3.5 / GPT-4o
        preferred = preferred or "arena"
    elif any(m in t for m in deep_markers) or word_count > 45:
        kind = "deep"
        # Pour les tâches de réflexion, on préfère l'Arène (Claude 3.5 Sonnet)
        preferred = preferred or "arena"
    else:
        kind = "conversation"

    complexity = 1
    if word_count > 18:
        complexity += 1
    if word_count > 45 or kind == "deep":
        complexity += 1
    if needs_realtime:
        complexity += 1

    if kind == "deep":
        priority = "smart"
        # Arena (Claude/GPT-4) peut prendre du temps. On lui laisse jusqu'à 120s pour réfléchir.
        timeout = float(os.getenv("PHOEBUS_BRAIN_SMART_TIMEOUT", "120"))
    elif kind == "command" or in_conversation or (streaming and kind == "conversation"):
        priority = "fast"
        timeout = float(os.getenv("PHOEBUS_BRAIN_FAST_TIMEOUT", "15"))
    else:
        priority = "balanced"
        timeout = float(os.getenv("PHOEBUS_BRAIN_TIMEOUT", "30"))

    return BrainProfile(
        kind=kind,
        priority=priority,
        preferred_provider=preferred,
        needs_realtime=needs_realtime,
        complexity=complexity,
        timeout_s=max(5.0, timeout),
    )


def _move_first(order: list[str], provider: str) -> list[str]:
    if provider not in order:
        return order
    return [provider] + [p for p in order if p != provider]


def _load_metrics() -> dict:
    try:
        if METRICS_FILE.exists():
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_metrics(data: dict) -> None:
    try:
        METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[BRAIN] impossible d'ecrire les metriques : {e}")


def record_provider_result(provider: str, ok: bool, latency_ms: float, error: str = "") -> None:
    if provider not in PROVIDERS:
        return
    data = _load_metrics()
    now = time.time()
    item = data.setdefault(provider, {})
    item["calls"] = int(item.get("calls", 0)) + 1
    item["last_ts"] = now
    item["last_latency_ms"] = round(float(latency_ms), 1)

    prev_avg = float(item.get("avg_latency_ms", latency_ms) or latency_ms)
    item["avg_latency_ms"] = round(prev_avg * 0.75 + float(latency_ms) * 0.25, 1)

    if ok:
        item["success"] = int(item.get("success", 0)) + 1
        item["failures_streak"] = 0
        item["last_error"] = ""
        item["cooldown_until"] = 0
    else:
        item["failure"] = int(item.get("failure", 0)) + 1
        streak = int(item.get("failures_streak", 0)) + 1
        item["failures_streak"] = streak
        item["last_error"] = str(error or "")[:220]
        
        # Détecter les erreurs de quota (429) et appliquer une cooldown longue
        error_lower = str(error or "").lower()
        is_quota_error = "429" in str(error) or "resource_exhausted" in error_lower or "quota" in error_lower
        
        if is_quota_error:
            # Erreur de quota : cooldown d'1 heure
            item["cooldown_until"] = now + QUOTA_COOLDOWN_SECONDS
        else:
            # Erreur classique : augmentation exponentielle avec max 3 minutes
            item["cooldown_until"] = now + min(180, FAIL_COOLDOWN_SECONDS * streak)
    _save_metrics(data)


def rank_provider_names(
    profile: BrainProfile,
    available: Optional[Iterable[str]] = None,
    order: Optional[Iterable[str]] = None,
    mode: Optional[str] = None,
    metrics: Optional[dict] = None,
    exclude_cooling: bool = True,
) -> list[str]:
    """Retourne les fournisseurs a tenter, dans l'ordre.
    
    Args:
        exclude_cooling: Si True (défaut), exclut les providers en cooldown.
                        Si False, les retourne en dernier (ancien comportement).
    """
    available_set = set(available or PROVIDERS)
    base = [p for p in (list(order) if order else configured_order()) if p in available_set]
    mode = mode or configured_mode()

    if profile.preferred_provider:
        base = _move_first(base, profile.preferred_provider)
    elif mode == "privacy":
        base = _move_first(base, "ollama")
    elif mode == "speed" or profile.priority == "fast":
        # Groq est souvent le meilleur compromis latence pour les reponses texte.
        base = _move_first(base, "groq")
    elif mode == "smart" or profile.priority == "smart":
        base = _move_first(base, "gemini")

    metrics = metrics if metrics is not None else _load_metrics()
    now = time.time()

    healthy = []
    cooling = []
    for provider in base:
        item = metrics.get(provider, {}) if isinstance(metrics, dict) else {}
        cooldown = float(item.get("cooldown_until", 0) or 0)
        if cooldown > now:
            cooling.append(provider)
        else:
            healthy.append(provider)
    
    if exclude_cooling:
        return healthy or cooling  # Si tout est en cooldown, tenter quand même le moins pire.
    else:
        return healthy + cooling  # Ancien comportement


def available_provider_names() -> list[str]:
    """Detecte les fournisseurs configures sans declencher d'appel reseau."""
    from PHOEBUS.config import (
        client, groq_client, grok_client, mistral_client,
        openai_client, kimi_client, arena_client, types
    )

    names = []
    if client and types:
        names.append("gemini")
    if groq_client:
        names.append("groq")
    if openai_client:
        names.append("openai")
    if mistral_client:
        names.append("mistral")
    if kimi_client:
        names.append("kimi")
    if grok_client:
        names.append("grok")
    if arena_client:
        names.append("arena")
    # Ollama est local : on le garde comme candidat meme s'il peut etre eteint.
    names.append("ollama")
    return names


def router_status() -> dict:
    return {
        "mode": configured_mode(),
        "order": configured_order(),
        "available": available_provider_names(),
        "metrics": _load_metrics(),
        "metrics_file": str(Path(METRICS_FILE)),
    }
