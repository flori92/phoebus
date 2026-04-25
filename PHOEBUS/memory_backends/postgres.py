"""Backend mémoire Postgres + pgvector (optionnel).

Pourquoi : la couche locale (JSON + ChromaDB) suffit pour 1 machine mais
ne scale pas — pas de sync multi-device, pas de backup gratuit, pas de
requête transversale. Postgres résout tout ça.

Activation (dans .env) :
    PHOEBUS_MEMORY_BACKEND=postgres
    DATABASE_URL=postgresql://user:pass@host:5432/jarvis

Pré-requis :
    pip install psycopg[binary]
    Dans la DB cible :
        CREATE EXTENSION IF NOT EXISTS vector;
        puis exécuter le schéma ci-dessous (appel auto via ensure_schema()).

API symétrique à `memory_unified` :
    remember(content, kind, importance, key)
    recall(query, limit) -> List[RecallResult]
    forget_key(key)
    note_correction(original, corrected)

L'embedding par défaut utilise Gemini (text-embedding-004, 768 dims). On
peut passer à sentence-transformers local en changeant `_embed`.
"""
import os
from dataclasses import dataclass
from typing import List, Optional


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ENABLED = os.getenv("PHOEBUS_MEMORY_BACKEND", "local").strip().lower() == "postgres"
EMBEDDING_DIMS = int(os.getenv("PHOEBUS_EMBEDDING_DIMS", "768"))


SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS jarvis_facts (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jarvis_memories (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,          -- event | correction | signal | fact-free
    importance  INT  NOT NULL DEFAULT 1,
    content     TEXT NOT NULL,
    embedding   vector({EMBEDDING_DIMS}),
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jarvis_memories_embedding_idx
    ON jarvis_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS jarvis_memories_kind_idx  ON jarvis_memories(kind);
CREATE INDEX IF NOT EXISTS jarvis_memories_imp_idx   ON jarvis_memories(importance DESC);

CREATE TABLE IF NOT EXISTS jarvis_profile_counters (
    key         TEXT PRIMARY KEY,
    count       INT  NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass
class RecallResult:
    source: str
    text: str
    importance: int = 1
    extra: Optional[dict] = None


# ── Connexion paresseuse ───────────────────────────────────────────────────

_conn = None
_schema_ok = False


def _psycopg():
    try:
        import psycopg
        return psycopg
    except Exception as e:
        print(f"[PG] psycopg non installé : {e}")
        return None


def _get_conn():
    global _conn
    if _conn is not None:
        return _conn
    if not DATABASE_URL:
        return None
    mod = _psycopg()
    if mod is None:
        return None
    try:
        _conn = mod.connect(DATABASE_URL, autocommit=True)
        return _conn
    except Exception as e:
        print(f"[PG] Connexion impossible : {e}")
        return None


def ensure_schema() -> bool:
    global _schema_ok
    if _schema_ok:
        return True
    conn = _get_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        _schema_ok = True
        return True
    except Exception as e:
        print(f"[PG] Schéma KO : {e}")
        return False


# ── Embedding ─────────────────────────────────────────────────────────────

def _embed(text: str) -> Optional[list]:
    """Calcule l'embedding du texte. Utilise Gemini text-embedding-004 par
    défaut. Renvoie None si indisponible — la ligne est alors stockée sans
    embedding et ne sera recherchable que par ILIKE."""
    if not text:
        return None
    try:
        from PHOEBUS.config import client
        if client is None:
            return None
        r = client.models.embed_content(
            model="text-embedding-004",
            contents=[text],
        )
        values = r.embeddings[0].values if hasattr(r, "embeddings") else None
        if values and len(values) == EMBEDDING_DIMS:
            return list(values)
    except Exception as e:
        print(f"[PG] Embedding KO : {e}")
    return None


# ── API publique ──────────────────────────────────────────────────────────

def remember(content: str, kind: str = "event", importance: int = 1,
             key: Optional[str] = None, source: str = "jarvis") -> bool:
    if not ENABLED or not ensure_schema():
        return False
    conn = _get_conn()
    if conn is None or not content:
        return False
    try:
        with conn.cursor() as cur:
            if kind == "fact" and key:
                cur.execute(
                    """INSERT INTO jarvis_facts (key, value, updated_at)
                       VALUES (%s, %s, now())
                       ON CONFLICT (key) DO UPDATE
                       SET value = EXCLUDED.value, updated_at = now()""",
                    (key, content),
                )
                return True

            emb = _embed(content)
            cur.execute(
                """INSERT INTO jarvis_memories (kind, importance, content, embedding, source)
                   VALUES (%s, %s, %s, %s, %s)""",
                (kind, importance, content, emb, source),
            )
        return True
    except Exception as e:
        print(f"[PG] remember : {e}")
        return False


def recall(query: str, limit: int = 5) -> List[RecallResult]:
    if not ENABLED or not ensure_schema():
        return []
    conn = _get_conn()
    if conn is None or not query:
        return []
    results: List[RecallResult] = []

    # 1. Faits exact / ILIKE.
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT key, value FROM jarvis_facts
                   WHERE key ILIKE %s OR value ILIKE %s LIMIT %s""",
                (f"%{query}%", f"%{query}%", limit),
            )
            for key, value in cur.fetchall():
                results.append(
                    RecallResult(source="fact", text=f"{key} : {value}", importance=2)
                )
    except Exception as e:
        print(f"[PG] recall facts : {e}")

    # 2. Mémoires par similarité cosinus.
    emb = _embed(query)
    try:
        with conn.cursor() as cur:
            if emb is not None:
                cur.execute(
                    """SELECT kind, importance, content
                       FROM jarvis_memories
                       WHERE embedding IS NOT NULL
                       ORDER BY embedding <=> %s::vector
                       LIMIT %s""",
                    (emb, limit),
                )
            else:
                cur.execute(
                    """SELECT kind, importance, content
                       FROM jarvis_memories
                       WHERE content ILIKE %s
                       ORDER BY importance DESC, created_at DESC LIMIT %s""",
                    (f"%{query}%", limit),
                )
            for kind, imp, content in cur.fetchall():
                results.append(
                    RecallResult(source="rag", text=content, importance=int(imp or 1),
                                 extra={"kind": kind}),
                )
    except Exception as e:
        print(f"[PG] recall memories : {e}")

    results.sort(key=lambda r: -r.importance)
    return results[:limit]


def forget_key(key: str) -> bool:
    if not ENABLED or not ensure_schema():
        return False
    conn = _get_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jarvis_facts WHERE key = %s", (key,))
            return cur.rowcount > 0
    except Exception as e:
        print(f"[PG] forget : {e}")
        return False


def note_correction(original: str, corrected: str) -> None:
    payload = (
        f"Floriace a corrigé une réponse. "
        f"Réponse initiale : « {original.strip()[:250]} ». "
        f"Correction : « {corrected.strip()[:250]} »."
    )
    remember(payload, kind="correction", importance=3, source="correction")
