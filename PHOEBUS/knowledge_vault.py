# PHOEBUS/knowledge_vault.py
"""Façade unifiée Multi-Backend pour les notes de PHOEBUS.

Abstrait les différences entre Obsidian et SiYuan derrière une interface
unique. Le code appelant (skills, mémoire, proactif) ne sait pas quel
backend tourne — il appelle `vault.*` et la façade route intelligemment.

Priorité : SiYuan API > Obsidian API > Obsidian filesystem.

Modes supportés :
  - SiYuan seul              (SIYUAN_ENABLED=1)
  - Obsidian seul            (OBSIDIAN_ENABLED=1, sans API key = filesystem pur)
  - Les deux en parallèle    (les deux ENABLED → SiYuan principal + Obsidian FS)
  - Aucun                    (tout désactivé, les skills retournent "non configuré")
"""

import asyncio
import os
from datetime import datetime
from typing import Optional


def _obsidian():
    try:
        from PHOEBUS import obsidian
        return obsidian
    except Exception:
        return None


def _siyuan():
    try:
        from PHOEBUS import siyuan
        return siyuan
    except Exception:
        return None


# ── État des backends ───────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Au moins un backend notes est configuré."""
    obs = _obsidian()
    sy = _siyuan()
    obs_ok = obs and obs.OBSIDIAN_ENABLED
    sy_ok = sy and sy.SIYUAN_ENABLED
    return bool(obs_ok or sy_ok)


def backends_summary() -> str:
    """Résumé rapide des backends actifs."""
    parts = []
    obs = _obsidian()
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED:
        parts.append("SiYuan")
    if obs and obs.OBSIDIAN_ENABLED:
        has_key = bool(obs.OBSIDIAN_API_KEY)
        has_vault = bool(obs._vault())
        mode = "API" if has_key else ("filesystem" if has_vault else "non configuré")
        parts.append(f"Obsidian ({mode})")
    return " + ".join(parts) if parts else "Aucun backend notes"


# ── CRUD Notes ──────────────────────────────────────────────────────────────

async def capture_note(content: str, title: str = "", tags: list[str] | None = None,
                        folder: str = "") -> str:
    """Crée une note rapide via le meilleur backend disponible."""
    # SiYuan en priorité s'il est actif et joignable
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED:
        if await sy.api_available():
            return await sy.capture_note(content, title=title, tags=tags, folder=folder)

    # Obsidian (API ou filesystem)
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.capture_note(content, title=title, tags=tags, folder=folder)

    return "Aucun backend notes configuré."


async def read_note(path: str) -> str | None:
    """Lit une note."""
    # SiYuan
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        result = await sy.read_doc_by_path(path)
        if result:
            return result

    # Obsidian
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.read_note(path)

    return None


async def write_note(path: str, content: str) -> bool:
    """Crée ou remplace une note."""
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        doc_id = await sy.create_doc(path, content)
        if doc_id:
            return True

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.write_note(path, content)

    return False


async def append_note(path: str, content: str) -> bool:
    """Ajoute du contenu à une note."""
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.append_note(path, content)
    return False


async def delete_note(path: str) -> bool:
    """Supprime une note."""
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.delete_note(path)
    return False


# ── Daily Notes ─────────────────────────────────────────────────────────────

async def get_daily_note(date: datetime | None = None) -> str | None:
    """Lit la daily note du jour."""
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        result = await sy.get_daily_note(date)
        if result:
            return result

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.get_daily_note(date)

    return None


async def append_daily(content: str, date: datetime | None = None) -> bool:
    """Ajoute du contenu à la daily note."""
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        if await sy.append_daily(content, date):
            return True

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.append_daily(content, date)

    return False


# ── Recherche ───────────────────────────────────────────────────────────────

async def search_text(query: str, context_length: int = 100) -> list[dict]:
    """Recherche textuelle dans tous les backends actifs."""
    results = []

    # SiYuan
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        sy_results = await sy.search_text(query, context_length)
        for r in sy_results:
            r["backend"] = "siyuan"
        results.extend(sy_results)

    # Obsidian
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        obs_results = await obs.search_text(query, context_length)
        for r in obs_results:
            r["backend"] = "obsidian"
        results.extend(obs_results)

    return results


async def search_semantic(query: str, n_results: int = 5) -> list[dict]:
    """Recherche sémantique dans tous les backends (ChromaDB)."""
    all_results = []

    # SiYuan ChromaDB
    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED:
        sy_results = await sy.search_vault_semantic(query, n_results=n_results)
        all_results.extend(sy_results)

    # Obsidian ChromaDB
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        obs_results = await obs.search_vault_semantic(query, n_results=n_results)
        for r in obs_results:
            r["source"] = "obsidian"
        all_results.extend(obs_results)

    # Trier par score décroissant et dédupliquer
    all_results.sort(key=lambda x: -(x.get("score", 0)))
    return all_results[:n_results]


# ── TODOs ───────────────────────────────────────────────────────────────────

async def find_todos(limit: int = 20) -> list[dict]:
    """Cherche les tâches incomplètes dans tous les backends."""
    todos = []

    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED and await sy.api_available():
        sy_todos = await sy.find_todos(limit=limit)
        for t in sy_todos:
            t["backend"] = "siyuan"
        todos.extend(sy_todos)

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        remaining = limit - len(todos)
        if remaining > 0:
            obs_todos = await obs.find_todos(limit=remaining)
            for t in obs_todos:
                t["backend"] = "obsidian"
            todos.extend(obs_todos)

    return todos[:limit]


# ── Indexation ──────────────────────────────────────────────────────────────

async def index_all(force: bool = False) -> dict:
    """Indexe tous les backends dans ChromaDB."""
    results = {}

    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED:
        results["siyuan"] = await sy.index_to_chroma(force=force)

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        results["obsidian"] = await obs.index_vault_to_chroma(force=force)

    # Totaux
    total_indexed = sum(r.get("indexed", 0) for r in results.values())
    total_skipped = sum(r.get("skipped", 0) for r in results.values())
    total_errors = sum(r.get("errors", 0) for r in results.values())

    results["total"] = {
        "indexed": total_indexed,
        "skipped": total_skipped,
        "errors": total_errors,
    }
    return results


# ── Ouvrir dans l'UI ────────────────────────────────────────────────────────

async def open_in_app(path: str) -> bool:
    """Ouvre une note dans l'UI de l'application (Obsidian)."""
    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        return await obs.open_note_in_obsidian(path)
    return False


# ── Statut ──────────────────────────────────────────────────────────────────

async def vault_status() -> dict:
    """Retourne l'état complet de tous les backends."""
    status = {"backends": backends_summary()}

    obs = _obsidian()
    if obs and obs.OBSIDIAN_ENABLED:
        status["obsidian"] = await obs.obsidian_status()

    sy = _siyuan()
    if sy and sy.SIYUAN_ENABLED:
        status["siyuan"] = await sy.siyuan_status()

    return status
