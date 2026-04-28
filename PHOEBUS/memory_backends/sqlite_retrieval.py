# PHOEBUS/memory_backends/sqlite_retrieval.py
"""Mémoire de secours SQLite pour remplacer Chroma quand il tombe.

Ce backend ne dépend que de la stdlib. Il stocke tous les souvenirs en local et
fait une recherche lexicale stable. Chroma reste meilleur pour la similarité,
mais SQLite évite de perdre la mémoire quand la base vectorielle est corrompue.
"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from PHOEBUS.config import BASE_DIR


DB_PATH = BASE_DIR / "logs" / "memory_fallback.sqlite3"


def ensure_schema(db_path: Path | None = None) -> bool:
    path = db_path or DB_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                )
                """
            )
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
                    "USING fts5(id UNINDEXED, text)"
                )
            except sqlite3.Error:
                pass
            conn.commit()
        return True
    except Exception as exc:
        print(f"[MEM] SQLite fallback indisponible : {exc}")
        return False


def store_memory(
    text: str,
    *,
    source: str = "conversation",
    importance: int = 1,
    timestamp: str,
    db_path: Path | None = None,
) -> bool:
    if not text or not ensure_schema(db_path):
        return False
    path = db_path or DB_PATH
    mem_id = f"mem_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    try:
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                INSERT INTO memories (id, text, source, timestamp, importance, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mem_id, text, source, timestamp, int(importance), time.time()),
            )
            try:
                conn.execute(
                    "INSERT INTO memories_fts (id, text) VALUES (?, ?)",
                    (mem_id, text),
                )
            except sqlite3.Error:
                pass
            conn.commit()
        return True
    except Exception as exc:
        print(f"[MEM] Écriture SQLite fallback impossible : {exc}")
        return False


def search_memory(query: str, *, limit: int = 5, db_path: Path | None = None) -> list[dict[str, Any]]:
    if not query or not ensure_schema(db_path):
        return []
    path = db_path or DB_PATH
    return _search_fts(path, query, limit) or _search_overlap(path, query, limit)


def status(db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or DB_PATH
    if not ensure_schema(path):
        return {"available": False, "count": 0, "path": str(path)}
    try:
        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"available": True, "count": int(count), "path": str(path)}
    except Exception:
        return {"available": False, "count": 0, "path": str(path)}


def _search_fts(path: Path, query: str, limit: int) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return []
    match = " OR ".join(f'"{token}"' for token in tokens[:8])
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT m.id, m.text, m.source, m.timestamp, m.importance
                FROM memories_fts f
                JOIN memories m ON m.id = f.id
                WHERE memories_fts MATCH ?
                ORDER BY bm25(memories_fts), m.importance DESC, m.created_at DESC
                LIMIT ?
                """,
                (match, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def _search_overlap(path: Path, query: str, limit: int) -> list[dict[str, Any]]:
    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, text, source, timestamp, importance
                FROM memories
                ORDER BY importance DESC, created_at DESC
                LIMIT 500
                """
            ).fetchall()
    except sqlite3.Error:
        return []

    scored = []
    for row in rows:
        text_tokens = set(_tokens(row["text"]))
        score = len(q_tokens & text_tokens) + int(row["importance"]) * 0.2
        if score > 0:
            scored.append((score, dict(row)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _score, row in scored[:limit]]


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\wÀ-ÿ]+", (text or "").lower()) if len(token) > 2]
