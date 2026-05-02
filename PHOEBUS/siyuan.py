# PHOEBUS/siyuan.py
"""Bridge SiYuan Note ↔ PHOEBUS.

SiYuan est un PKM open source (AGPL-3.0) avec une API REST Kernel native.
Toutes les requêtes sont des POST vers http://127.0.0.1:6806/api/...

Ce bridge offre :
  - CRUD notes (via Markdown)
  - Recherche full-text et SQL
  - Gestion notebooks
  - Daily notes
  - Indexation dans ChromaDB pour la recherche sémantique

Authentification : token dans Settings > About > API Token.
"""

import asyncio
import os
import re
import time
from datetime import datetime
from typing import Optional

import requests

from PHOEBUS.config import BASE_DIR


# ── Configuration ───────────────────────────────────────────────────────────

SIYUAN_ENABLED = os.getenv("SIYUAN_ENABLED", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
SIYUAN_API_URL = os.getenv("SIYUAN_API_URL", "http://127.0.0.1:6806").strip().rstrip("/")
SIYUAN_API_TOKEN = os.getenv("SIYUAN_API_TOKEN", "").strip()
# Notebook par défaut pour les captures rapides (ID ou nom)
SIYUAN_DEFAULT_NOTEBOOK = os.getenv("SIYUAN_DEFAULT_NOTEBOOK", "").strip()
SIYUAN_DAILY_PATH = os.getenv("SIYUAN_DAILY_PATH", "/daily note/{{now | date \"2006-01-02\"}}").strip()

_CHROMA_COLLECTION_NAME = "PHOEBUS_siyuan_vault"
_last_index_ts: float = 0.0

# Cache notebook résolu
_default_notebook_id: str | None = None


# ── Helpers internes ────────────────────────────────────────────────────────

def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if SIYUAN_API_TOKEN:
        h["Authorization"] = f"Token {SIYUAN_API_TOKEN}"
    return h


def _post(endpoint: str, payload: dict | None = None) -> dict | None:
    """Appel POST vers le Kernel API SiYuan. Retourne data ou None."""
    url = f"{SIYUAN_API_URL}{endpoint}"
    try:
        r = requests.post(url, json=payload or {}, headers=_headers(), timeout=8)
        if r.status_code != 200:
            return None
        j = r.json()
        if j.get("code", -1) != 0:
            print(f"[SIYUAN] {endpoint} erreur : {j.get('msg', '?')}")
            return None
        return j.get("data")
    except Exception as e:
        print(f"[SIYUAN] POST {endpoint} KO : {e}")
        return None


# ── API disponible ? ────────────────────────────────────────────────────────

_api_available: bool | None = None


async def api_available() -> bool:
    """Teste si SiYuan est joignable."""
    global _api_available
    if _api_available is not None:
        return _api_available
    try:
        data = await asyncio.to_thread(
            lambda: _post("/api/system/version")
        )
        _api_available = data is not None
        if _api_available:
            print(f"[SIYUAN] Connecté — version {data}")
    except Exception:
        _api_available = False
    return _api_available


def reset_api_cache():
    global _api_available, _default_notebook_id
    _api_available = None
    _default_notebook_id = None


# ── Notebooks ───────────────────────────────────────────────────────────────

async def list_notebooks() -> list[dict]:
    """Liste tous les notebooks SiYuan."""
    data = await asyncio.to_thread(
        lambda: _post("/api/notebook/lsNotebooks")
    )
    if data and "notebooks" in data:
        return data["notebooks"]
    return []


async def _resolve_default_notebook() -> str | None:
    """Résout l'ID du notebook par défaut."""
    global _default_notebook_id
    if _default_notebook_id:
        return _default_notebook_id

    notebooks = await list_notebooks()
    if not notebooks:
        return None

    # Si un nom ou ID est configuré, chercher
    if SIYUAN_DEFAULT_NOTEBOOK:
        for nb in notebooks:
            if nb.get("id") == SIYUAN_DEFAULT_NOTEBOOK or \
               nb.get("name", "").lower() == SIYUAN_DEFAULT_NOTEBOOK.lower():
                _default_notebook_id = nb["id"]
                return _default_notebook_id

    # Sinon prendre le premier ouvert
    for nb in notebooks:
        if not nb.get("closed", False):
            _default_notebook_id = nb["id"]
            return _default_notebook_id

    # Fallback : premier tout court
    if notebooks:
        _default_notebook_id = notebooks[0]["id"]
    return _default_notebook_id


# ── CRUD Documents ──────────────────────────────────────────────────────────

async def create_doc(path: str, markdown: str, notebook_id: str = "") -> str | None:
    """Crée un document avec du contenu Markdown.

    Retourne l'ID du document ou None.
    """
    nb_id = notebook_id or await _resolve_default_notebook()
    if not nb_id:
        return None
    # S'assurer que le path commence par /
    if not path.startswith("/"):
        path = "/" + path
    data = await asyncio.to_thread(
        lambda: _post("/api/filetree/createDocWithMd", {
            "notebook": nb_id,
            "path": path,
            "markdown": markdown,
        })
    )
    return data if isinstance(data, str) else (data.get("id") if isinstance(data, dict) else None)


async def read_doc(doc_id: str) -> str | None:
    """Lit un document et retourne son contenu Markdown."""
    data = await asyncio.to_thread(
        lambda: _post("/api/export/exportMdContent", {"id": doc_id})
    )
    if data and "content" in data:
        return data["content"]
    return None


async def read_doc_by_path(path: str, notebook_id: str = "") -> str | None:
    """Lit un document par son chemin (path) humain."""
    nb_id = notebook_id or await _resolve_default_notebook()
    if not nb_id:
        return None
    # Chercher l'ID du doc par path
    doc_id = await _get_doc_id_by_path(path, nb_id)
    if not doc_id:
        return None
    return await read_doc(doc_id)


async def _get_doc_id_by_path(path: str, notebook_id: str) -> str | None:
    """Résout le path humain vers un ID de bloc racine."""
    if not path.startswith("/"):
        path = "/" + path
    data = await asyncio.to_thread(
        lambda: _post("/api/filetree/getIDsByHPath", {
            "notebook": notebook_id,
            "path": path,
        })
    )
    if data and isinstance(data, list) and data:
        return data[0]
    return None


async def append_block(parent_id: str, markdown: str) -> bool:
    """Ajoute un bloc Markdown enfant à un bloc existant."""
    data = await asyncio.to_thread(
        lambda: _post("/api/block/appendBlock", {
            "parentID": parent_id,
            "data": markdown,
            "dataType": "markdown",
        })
    )
    return data is not None


async def delete_doc(doc_id: str) -> bool:
    """Supprime un document par son ID."""
    data = await asyncio.to_thread(
        lambda: _post("/api/filetree/removeDocByID", {"id": doc_id})
    )
    return data is not None


# ── Recherche ───────────────────────────────────────────────────────────────

async def search_fulltext(query: str, page: int = 1) -> list[dict]:
    """Recherche full-text dans tous les blocs."""
    data = await asyncio.to_thread(
        lambda: _post("/api/search/fullTextSearchBlock", {
            "query": query,
            "page": page,
        })
    )
    if data and "blocks" in data:
        return data["blocks"]
    return []


async def search_sql(sql: str) -> list[dict]:
    """Exécute une requête SQL sur la base de blocs.

    Exemple : SELECT * FROM blocks WHERE content LIKE '%architecture%' LIMIT 10
    """
    if not sql.strip().upper().startswith("SELECT"):
        return []  # Sécurité : uniquement des SELECT
    data = await asyncio.to_thread(
        lambda: _post("/api/query/sql", {"stmt": sql})
    )
    return data if isinstance(data, list) else []


async def search_text(query: str, context_length: int = 100) -> list[dict]:
    """Interface unifiée de recherche (compatible avec le format Obsidian)."""
    blocks = await search_fulltext(query)
    results = []
    seen_docs = set()
    for block in blocks[:20]:
        doc_path = block.get("hPath", block.get("path", "?"))
        if doc_path in seen_docs:
            continue
        seen_docs.add(doc_path)
        content = block.get("content", "")
        # Nettoyer le HTML basique des résultats SiYuan
        content = re.sub(r"<[^>]+>", "", content)
        results.append({
            "filename": doc_path,
            "matches": [{"context": content[:context_length]}],
            "block_id": block.get("id", ""),
        })
    return results


# ── Daily Notes ─────────────────────────────────────────────────────────────

async def get_daily_note(date: datetime | None = None) -> str | None:
    """Lit la daily note du jour."""
    d = date or datetime.now()
    path = f"/daily note/{d.strftime('%Y-%m-%d')}"
    return await read_doc_by_path(path)


async def append_daily(content: str, date: datetime | None = None) -> bool:
    """Ajoute du contenu à la daily note du jour."""
    d = date or datetime.now()
    path = f"/daily note/{d.strftime('%Y-%m-%d')}"
    nb_id = await _resolve_default_notebook()
    if not nb_id:
        return False
    doc_id = await _get_doc_id_by_path(path, nb_id)
    if not doc_id:
        # Créer la daily note si elle n'existe pas
        doc_id = await create_doc(path, f"# {d.strftime('%A %d %B %Y')}\n\n")
        if not doc_id:
            return False
    return await append_block(doc_id, content)


# ── Capture rapide ──────────────────────────────────────────────────────────

async def capture_note(content: str, title: str = "", tags: list[str] | None = None,
                        folder: str = "") -> str:
    """Crée une note rapide dans SiYuan.

    Retourne le chemin de la note créée.
    """
    now = datetime.now()
    if not title:
        title = f"Note {now.strftime('%Y-%m-%d %H:%M')}"
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
    target_folder = folder or "Inbox"
    path = f"/{target_folder}/{safe_title}"

    tag_str = ""
    if tags:
        tag_str = " ".join(f"#{t}" for t in tags)

    body = f"# {title}\n\n{content}\n"
    if tag_str:
        body += f"\n{tag_str}\n"

    doc_id = await create_doc(path, body)
    return path if doc_id else "Erreur de création"


# ── TODOs ───────────────────────────────────────────────────────────────────

async def find_todos(limit: int = 20) -> list[dict]:
    """Cherche les tâches incomplètes via SQL."""
    results = await search_sql(
        f"SELECT * FROM blocks WHERE type='i' AND subtype='t' "
        f"AND markdown LIKE '%[ ]%' ORDER BY updated DESC LIMIT {limit}"
    )
    todos = []
    for block in results:
        text = block.get("markdown", block.get("content", ""))
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("- [ ]", "").strip()
        todos.append({
            "file": block.get("hPath", "?"),
            "line": 0,
            "text": text,
            "block_id": block.get("id", ""),
        })
    return todos


# ═══════════════════════════════════════════════════════════════════════════
# INDEXATION DANS CHROMADB
# ═══════════════════════════════════════════════════════════════════════════

_vault_collection = None


def _get_vault_collection():
    """Renvoie la collection ChromaDB dédiée à SiYuan."""
    global _vault_collection
    if _vault_collection is not None:
        return _vault_collection
    try:
        import chromadb
        from PHOEBUS.rag_memory import get_google_embedding_function, DB_PATH
        client = chromadb.PersistentClient(path=DB_PATH)
        emb_fn = get_google_embedding_function()
        _vault_collection = client.get_or_create_collection(
            name=_CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=emb_fn,
        )
        return _vault_collection
    except Exception as e:
        print(f"[SIYUAN] ChromaDB indisponible : {e}")
        return None


def _chunk_text(text: str, max_len: int = 1500, overlap: int = 200) -> list[str]:
    """Découpe un texte en chunks."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_len
        chunk = text[start:end]
        if end < len(text):
            last_nl = chunk.rfind("\n")
            if last_nl > max_len // 2:
                chunk = chunk[:last_nl]
                end = start + last_nl
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 30]


async def index_to_chroma(force: bool = False) -> dict:
    """Indexe les documents SiYuan dans ChromaDB via l'API SQL.

    Récupère tous les blocs de type document/paragraphe et les indexe.
    """
    global _last_index_ts
    now = time.time()
    interval = int(os.getenv("SIYUAN_INDEX_INTERVAL", "3600"))
    if not force and (now - _last_index_ts) < interval:
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "trop récent"}

    if not await api_available():
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "SiYuan non joignable"}

    collection = await asyncio.to_thread(_get_vault_collection)
    if collection is None:
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "ChromaDB indisponible"}

    _last_index_ts = now
    t0 = time.time()
    indexed = 0
    skipped = 0
    errors = 0

    # Récupérer les IDs existants
    existing_ids = set()
    try:
        existing = collection.get(include=[])
        existing_ids = set(existing.get("ids", []))
    except Exception:
        pass

    # Récupérer les documents via SQL (blocs de type 'd' = document)
    docs = await search_sql(
        "SELECT id, content, hPath, updated FROM blocks WHERE type='d' "
        "ORDER BY updated DESC LIMIT 500"
    )

    for doc in docs:
        try:
            doc_id_sy = doc.get("id", "")
            hpath = doc.get("hPath", "?")
            updated = doc.get("updated", "")

            # Exporter le contenu Markdown complet du document
            md_content = await read_doc(doc_id_sy)
            if not md_content or len(md_content.strip()) < 20:
                skipped += 1
                continue

            chunks = _chunk_text(md_content)
            for i, chunk in enumerate(chunks):
                chunk_id = f"sy_{doc_id_sy}_{updated}_{i}"
                if chunk_id in existing_ids:
                    skipped += 1
                    continue

                # Nettoyer les anciennes versions
                old_prefix = f"sy_{doc_id_sy}_"
                old_ids = [eid for eid in existing_ids if eid.startswith(old_prefix)]
                if old_ids:
                    try:
                        collection.delete(ids=old_ids)
                        existing_ids -= set(old_ids)
                    except Exception:
                        pass

                metadata = {
                    "source": "siyuan",
                    "file": hpath,
                    "chunk_index": i,
                    "timestamp": updated,
                    "doc_id": doc_id_sy,
                }
                collection.add(
                    documents=[chunk],
                    metadatas=[metadata],
                    ids=[chunk_id],
                )
                existing_ids.add(chunk_id)
                indexed += 1

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"[SIYUAN] Erreur indexation : {e}")

    duration = round(time.time() - t0, 1)
    print(f"[SIYUAN] Indexation terminée : {indexed} chunks, {skipped} ignorés, {errors} erreurs ({duration}s)")
    return {"indexed": indexed, "skipped": skipped, "errors": errors, "duration_s": duration}


async def search_vault_semantic(query: str, n_results: int = 5) -> list[dict]:
    """Recherche sémantique dans les notes SiYuan indexées."""
    collection = await asyncio.to_thread(_get_vault_collection)
    if collection is None:
        return []
    try:
        results = collection.query(query_texts=[query], n_results=n_results)
        if not results or not results.get("documents") or not results["documents"][0]:
            return []
        items = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            dist = results["distances"][0][i] if results.get("distances") else 0
            items.append({
                "file": meta.get("file", "?"),
                "text": doc[:500],
                "score": round(1 - dist, 3) if dist else 0,
                "tags": "",
                "source": "siyuan",
            })
        return items
    except Exception as e:
        print(f"[SIYUAN] Recherche sémantique KO : {e}")
        return []


# ── Notifications dans SiYuan ───────────────────────────────────────────────

async def push_notification(msg: str, timeout_ms: int = 7000) -> bool:
    """Envoie une notification visible dans l'UI SiYuan."""
    data = await asyncio.to_thread(
        lambda: _post("/api/notification/pushMsg", {
            "msg": msg,
            "timeout": timeout_ms,
        })
    )
    return data is not None


# ── Statut ──────────────────────────────────────────────────────────────────

async def siyuan_status() -> dict:
    """Retourne l'état de l'intégration SiYuan."""
    api_ok = await api_available()
    collection = await asyncio.to_thread(_get_vault_collection)
    indexed_count = 0
    if collection:
        try:
            indexed_count = collection.count()
        except Exception:
            pass
    notebooks = await list_notebooks() if api_ok else []
    return {
        "enabled": SIYUAN_ENABLED,
        "api_available": api_ok,
        "api_url": SIYUAN_API_URL,
        "notebooks": len(notebooks),
        "indexed_chunks": indexed_count,
        "last_index_ts": _last_index_ts,
    }

