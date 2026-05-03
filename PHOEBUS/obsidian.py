# PHOEBUS/obsidian.py
"""Bridge Obsidian ↔ PHOEBUS.

Deux modes de fonctionnement (fallback automatique) :
  1. **API REST** — via le plugin « Local REST API » d'Obsidian.
     CRUD complet, recherche, commandes Obsidian, periodic notes.
  2. **Filesystem** — lecture/écriture directe des .md dans le vault.
     Fonctionne même quand Obsidian est fermé, mais pas de recherche.

Le bridge expose aussi :
  - `index_vault_to_chroma()` : indexe tous les .md dans ChromaDB pour
    enrichir la mémoire RAG de Phoebus avec le contenu du vault.
  - `search_vault_semantique()` : recherche sémantique dans les notes
    indexées (via la collection ChromaDB dédiée).
"""

import asyncio
import os
import re
import subprocess
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from PHOEBUS.config import BASE_DIR


# ── Configuration ───────────────────────────────────────────────────────────

OBSIDIAN_ENABLED = os.getenv("OBSIDIAN_ENABLED", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
OBSIDIAN_API_URL = os.getenv("OBSIDIAN_API_URL", "https://127.0.0.1:27124").strip()
OBSIDIAN_API_KEY = os.getenv("OBSIDIAN_API_KEY", "").strip()
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
OBSIDIAN_VAULT_NAME = os.getenv("OBSIDIAN_VAULT_NAME", "").strip()
OBSIDIAN_DEFAULT_FOLDER = os.getenv("OBSIDIAN_DEFAULT_FOLDER", "Inbox").strip()
OBSIDIAN_DAILY_FORMAT = os.getenv("OBSIDIAN_DAILY_FORMAT", "%Y-%m-%d").strip()
# Intervalle minimal (secondes) entre deux indexations complètes du vault.
OBSIDIAN_INDEX_INTERVAL = int(os.getenv("OBSIDIAN_INDEX_INTERVAL", "3600"))

_CHROMA_COLLECTION_NAME = "PHOEBUS_obsidian_vault"
_last_index_ts: float = 0.0


# ── Helpers internes ────────────────────────────────────────────────────────

def _headers(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {OBSIDIAN_API_KEY}"}
    if extra:
        h.update(extra)
    return h


def _api(method: str, path: str, **kwargs) -> requests.Response | None:
    """Appel HTTP vers le plugin Local REST API. Retourne None si KO."""
    if not OBSIDIAN_API_KEY:
        return None
    url = f"{OBSIDIAN_API_URL}{path}"
    kwargs.setdefault("headers", _headers())
    kwargs.setdefault("verify", False)
    kwargs.setdefault("timeout", 8)
    try:
        return getattr(requests, method)(url, **kwargs)
    except Exception as e:
        print(f"[OBSIDIAN] API {method.upper()} {path} KO : {e}")
        return None


def _vault() -> Path | None:
    if OBSIDIAN_VAULT_PATH:
        p = Path(OBSIDIAN_VAULT_PATH).expanduser()
        if p.is_dir():
            return p
    return None


def _ensure_folder(vault: Path, folder: str) -> Path:
    target = vault / folder
    target.mkdir(parents=True, exist_ok=True)
    return target


# ── API disponible ? ────────────────────────────────────────────────────────

_api_available: bool | None = None


async def api_available() -> bool:
    """Teste si le plugin REST API est joignable."""
    global _api_available
    if _api_available is not None:
        return _api_available
    try:
        r = await asyncio.to_thread(
            lambda: _api("get", "/")
        )
        _api_available = r is not None and r.status_code == 200
    except Exception:
        _api_available = False
    return _api_available


def reset_api_cache():
    global _api_available
    _api_available = None


# ── CRUD Notes ──────────────────────────────────────────────────────────────

async def read_note(path: str) -> str | None:
    """Lit une note. `path` est relatif au vault (ex: 'Projets/Phoebus.md')."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api("get", f"/vault/{urllib.parse.quote(path, safe='/')}")
        )
        if r and r.status_code == 200:
            return r.text
    # Fallback filesystem
    vault = _vault()
    if vault:
        fp = vault / path
        if fp.exists():
            return fp.read_text(encoding="utf-8")
    return None


async def read_note_json(path: str) -> dict | None:
    """Lit une note avec métadonnées (frontmatter, tags, stats)."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api(
                "get",
                f"/vault/{urllib.parse.quote(path, safe='/')}",
                headers=_headers({"Accept": "application/vnd.olrapi.note+json"}),
            )
        )
        if r and r.status_code == 200:
            return r.json()
    return None


async def write_note(path: str, content: str) -> bool:
    """Crée ou remplace une note."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api(
                "put",
                f"/vault/{urllib.parse.quote(path, safe='/')}",
                headers=_headers({"Content-Type": "text/markdown"}),
                data=content.encode("utf-8"),
            )
        )
        return r is not None and r.status_code in (200, 204)
    vault = _vault()
    if vault:
        fp = vault / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return True
    return False


async def append_note(path: str, content: str) -> bool:
    """Ajoute du contenu à la fin d'une note existante."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api(
                "post",
                f"/vault/{urllib.parse.quote(path, safe='/')}",
                headers=_headers({"Content-Type": "text/markdown"}),
                data=content.encode("utf-8"),
            )
        )
        return r is not None and r.status_code in (200, 204)
    vault = _vault()
    if vault:
        fp = vault / path
        if fp.exists():
            with open(fp, "a", encoding="utf-8") as f:
                f.write("\n" + content)
            return True
    return False


async def delete_note(path: str) -> bool:
    """Supprime une note."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api("delete", f"/vault/{urllib.parse.quote(path, safe='/')}")
        )
        return r is not None and r.status_code == 204
    vault = _vault()
    if vault:
        fp = vault / path
        if fp.exists():
            fp.unlink()
            return True
    return False


# ── Recherche ───────────────────────────────────────────────────────────────

async def search_text(query: str, context_length: int = 100) -> list[dict]:
    """Recherche textuelle dans le vault via l'API REST."""
    if not await api_available():
        return await _search_filesystem(query)
    r = await asyncio.to_thread(
        lambda: _api(
            "post",
            f"/search/simple/?query={urllib.parse.quote(query)}&contextLength={context_length}",
        )
    )
    if r and r.status_code == 200:
        return r.json() or []
    return []


async def _search_filesystem(query: str) -> list[dict]:
    """Recherche basique par grep sur le filesystem."""
    vault = _vault()
    if not vault:
        return []
    results = []
    q_lower = query.lower()
    for md_file in vault.rglob("*.md"):
        if ".obsidian" in str(md_file):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            if q_lower in text.lower():
                rel = str(md_file.relative_to(vault))
                # Trouver le contexte autour du match
                idx = text.lower().find(q_lower)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(query) + 50)
                results.append({
                    "filename": rel,
                    "matches": [{"context": text[start:end]}],
                })
        except Exception:
            continue
    return results


# ── Daily Notes ─────────────────────────────────────────────────────────────

def _daily_path(date: datetime | None = None) -> str:
    d = date or datetime.now()
    filename = d.strftime(OBSIDIAN_DAILY_FORMAT) + ".md"
    return f"Daily Notes/{filename}"


async def get_daily_note(date: datetime | None = None) -> str | None:
    """Lit la daily note du jour (ou d'une date donnée)."""
    # Essayer l'API periodic d'abord
    if await api_available():
        r = await asyncio.to_thread(lambda: _api("get", "/periodic/daily/"))
        if r and r.status_code == 200:
            return r.text
    return await read_note(_daily_path(date))


async def append_daily(content: str, date: datetime | None = None) -> bool:
    """Ajoute du contenu à la daily note."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api(
                "post",
                "/periodic/daily/",
                headers=_headers({"Content-Type": "text/markdown"}),
                data=content.encode("utf-8"),
            )
        )
        if r and r.status_code in (200, 204):
            return True
    return await append_note(_daily_path(date), content)


# ── Tags ────────────────────────────────────────────────────────────────────

async def list_tags() -> list[dict]:
    """Liste tous les tags du vault avec leurs compteurs."""
    if not await api_available():
        return []
    r = await asyncio.to_thread(lambda: _api("get", "/tags/"))
    if r and r.status_code == 200:
        return (r.json() or {}).get("tags", [])
    return []


# ── Commandes Obsidian ──────────────────────────────────────────────────────

async def execute_command(command_id: str) -> bool:
    """Exécute une commande Obsidian (ex: 'daily-notes:open')."""
    if not await api_available():
        return False
    r = await asyncio.to_thread(
        lambda: _api("post", f"/commands/{urllib.parse.quote(command_id)}/")
    )
    return r is not None and r.status_code == 204


async def open_note_in_obsidian(path: str) -> bool:
    """Ouvre une note dans l'UI Obsidian via l'API ou le protocole URI."""
    if await api_available():
        r = await asyncio.to_thread(
            lambda: _api("post", f"/open/{urllib.parse.quote(path, safe='/')}")
        )
        if r and r.status_code == 200:
            return True
    # Fallback URI protocol
    if OBSIDIAN_VAULT_NAME:
        vault_enc = urllib.parse.quote(OBSIDIAN_VAULT_NAME)
        file_enc = urllib.parse.quote(path.replace(".md", ""))
        uri = f"obsidian://open?vault={vault_enc}&file={file_enc}"
        try:
            subprocess.Popen(["open", uri])
            return True
        except Exception:
            pass
    return False


# ── Listing ─────────────────────────────────────────────────────────────────

async def list_files(folder: str = "") -> list[str]:
    """Liste les fichiers dans un dossier du vault."""
    if await api_available():
        path = f"/vault/{urllib.parse.quote(folder, safe='/')}".rstrip("/") + "/"
        r = await asyncio.to_thread(lambda: _api("get", path))
        if r and r.status_code == 200:
            return (r.json() or {}).get("files", [])
    vault = _vault()
    if vault:
        target = vault / folder if folder else vault
        if target.is_dir():
            return [
                str(f.relative_to(vault))
                for f in target.iterdir()
                if not f.name.startswith(".")
            ]
    return []


# ── Capture vocale rapide ───────────────────────────────────────────────────

async def capture_note(content: str, title: str = "", tags: list[str] | None = None,
                        folder: str = "") -> str:
    """Crée une note rapide horodatée dans le vault.

    Retourne le chemin de la note créée.
    """
    now = datetime.now()
    if not title:
        title = f"Note {now.strftime('%Y-%m-%d %H:%M')}"
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
    target_folder = folder or OBSIDIAN_DEFAULT_FOLDER
    path = f"{target_folder}/{safe_title}.md"

    tag_str = ""
    if tags:
        tag_str = ", ".join(tags)
    frontmatter = (
        f"---\n"
        f"date: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"source: phoebus\n"
    )
    if tag_str:
        frontmatter += f"tags: [{tag_str}]\n"
    frontmatter += "---\n\n"

    body = f"# {title}\n\n{content}\n"
    full_content = frontmatter + body

    await write_note(path, full_content)
    return path


# ── TODOs ───────────────────────────────────────────────────────────────────

async def find_todos(limit: int = 20) -> list[dict]:
    """Cherche les tâches incomplètes (- [ ]) dans le vault."""
    vault = _vault()
    if not vault:
        return []
    todos = []
    for md_file in vault.rglob("*.md"):
        if ".obsidian" in str(md_file):
            continue
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
            rel = str(md_file.relative_to(vault))
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    todos.append({
                        "file": rel,
                        "line": i + 1,
                        "text": stripped[5:].strip(),
                    })
                    if len(todos) >= limit:
                        return todos
        except Exception:
            continue
    return todos


# ═══════════════════════════════════════════════════════════════════════════
# INDEXATION DU VAULT DANS CHROMADB (Mémoire vectorielle)
# ═══════════════════════════════════════════════════════════════════════════

_vault_collection = None


def _get_vault_collection():
    """Renvoie la collection ChromaDB dédiée au vault Obsidian."""
    global _vault_collection
    if _vault_collection is not None:
        return _vault_collection
    try:
        import chromadb
        from PHOEBUS.rag_memory import get_local_embedding_function, DB_PATH
        client = chromadb.PersistentClient(path=DB_PATH)
        emb_fn = get_local_embedding_function()
        _vault_collection = client.get_or_create_collection(
            name=_CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=emb_fn,
        )
        return _vault_collection
    except Exception as e:
        print(f"[OBSIDIAN] ChromaDB indisponible pour le vault : {e}")
        return None


def _chunk_text(text: str, max_len: int = 1500, overlap: int = 200) -> list[str]:
    """Découpe un texte en chunks avec chevauchement pour le RAG."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_len
        chunk = text[start:end]
        # Essayer de couper sur un saut de ligne
        if end < len(text):
            last_nl = chunk.rfind("\n")
            if last_nl > max_len // 2:
                chunk = chunk[:last_nl]
                end = start + last_nl
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 30]


def _extract_frontmatter(text: str) -> dict:
    """Extrait le frontmatter YAML basique d'une note markdown."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    fm_block = text[3:end].strip()
    meta = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip("[]").strip()
    return meta


async def index_vault_to_chroma(force: bool = False) -> dict:
    """Indexe tous les .md du vault dans la collection ChromaDB dédiée.

    Retour : {"indexed": N, "skipped": M, "errors": E, "duration_s": D}

    L'indexation est incrémentale : les fichiers déjà indexés et non modifiés
    sont ignorés (comparaison mtime via l'ID du document).
    """
    global _last_index_ts
    now = time.time()
    if not force and (now - _last_index_ts) < OBSIDIAN_INDEX_INTERVAL:
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "trop récent"}

    vault = _vault()
    if not vault:
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "vault non configuré"}

    collection = await asyncio.to_thread(_get_vault_collection)
    if collection is None:
        return {"indexed": 0, "skipped": 0, "errors": 0, "message": "ChromaDB indisponible"}

    _last_index_ts = now
    t0 = time.time()
    indexed = 0
    skipped = 0
    errors = 0

    # Récupérer les IDs existants pour l'incrémental
    existing_ids = set()
    try:
        existing = collection.get(include=[])
        existing_ids = set(existing.get("ids", []))
    except Exception:
        pass

    md_files = list(vault.rglob("*.md"))
    for md_file in md_files:
        if ".obsidian" in str(md_file) or ".trash" in str(md_file):
            skipped += 1
            continue
        try:
            rel = str(md_file.relative_to(vault))
            mtime = int(md_file.stat().st_mtime)
            text = md_file.read_text(encoding="utf-8")
            if len(text.strip()) < 20:
                skipped += 1
                continue

            fm = _extract_frontmatter(text)
            chunks = _chunk_text(text)

            for i, chunk in enumerate(chunks):
                doc_id = f"obs_{rel}_{mtime}_{i}"
                if doc_id in existing_ids:
                    skipped += 1
                    continue

                # Nettoyer les anciennes versions de ce fichier
                old_prefix = f"obs_{rel}_"
                old_ids = [eid for eid in existing_ids if eid.startswith(old_prefix)]
                if old_ids:
                    try:
                        collection.delete(ids=old_ids)
                        existing_ids -= set(old_ids)
                    except Exception:
                        pass

                metadata = {
                    "source": "obsidian",
                    "file": rel,
                    "chunk_index": i,
                    "timestamp": datetime.fromtimestamp(mtime).isoformat(),
                    "tags": fm.get("tags", ""),
                }
                collection.add(
                    documents=[chunk],
                    metadatas=[metadata],
                    ids=[doc_id],
                )
                existing_ids.add(doc_id)
                indexed += 1

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"[OBSIDIAN] Erreur indexation {md_file.name}: {e}")

    duration = round(time.time() - t0, 1)
    print(f"[OBSIDIAN] Indexation terminée : {indexed} chunks, {skipped} ignorés, {errors} erreurs ({duration}s)")
    return {"indexed": indexed, "skipped": skipped, "errors": errors, "duration_s": duration}


async def search_vault_semantic(query: str, n_results: int = 5) -> list[dict]:
    """Recherche sémantique dans les notes Obsidian indexées dans ChromaDB.

    Retour : liste de dict avec {file, text, score, tags}.
    """
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
                "tags": meta.get("tags", ""),
            })
        return items
    except Exception as e:
        print(f"[OBSIDIAN] Recherche sémantique KO : {e}")
        return []


# ── Statut ──────────────────────────────────────────────────────────────────

async def obsidian_status() -> dict:
    """Retourne l'état de l'intégration Obsidian."""
    vault = _vault()
    api_ok = await api_available()
    collection = await asyncio.to_thread(_get_vault_collection)
    indexed_count = 0
    if collection:
        try:
            indexed_count = collection.count()
        except Exception:
            pass
    return {
        "enabled": OBSIDIAN_ENABLED,
        "api_available": api_ok,
        "vault_path": str(vault) if vault else None,
        "vault_exists": vault is not None and vault.is_dir(),
        "indexed_chunks": indexed_count,
        "last_index_ts": _last_index_ts,
    }
