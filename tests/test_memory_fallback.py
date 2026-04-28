"""Tests de la mémoire SQLite de secours."""

from pathlib import Path

import PHOEBUS.memory_backends.sqlite_retrieval as sqlite_retrieval
import PHOEBUS.rag_memory as rag_memory


def test_sqlite_retrieval_store_and_search(tmp_path):
    db_path = tmp_path / "memory.sqlite3"

    assert sqlite_retrieval.store_memory(
        "Floriace préfère les réponses rapides et actionnables",
        source="test",
        importance=2,
        timestamp="2026-04-29T10:00:00",
        db_path=db_path,
    )

    rows = sqlite_retrieval.search_memory("réponses rapides", limit=3, db_path=db_path)

    assert rows
    assert "réponses rapides" in rows[0]["text"]


def test_rag_memory_utilise_sqlite_si_chroma_indisponible(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.sqlite3"
    monkeypatch.setattr(sqlite_retrieval, "DB_PATH", db_path)
    monkeypatch.setattr(rag_memory, "init_chroma", lambda: False)

    assert rag_memory.stocker_souvenir(
        "Phoebus doit rester stable si Chroma casse",
        source="test",
        importance=3,
    )
    result = rag_memory.rechercher_souvenirs("Chroma stable", n_results=2)

    assert "Chroma casse" in result
