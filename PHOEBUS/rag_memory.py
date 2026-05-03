# PHOEBUS/rag_memory.py
"""
Mémoire Vectorielle Long Terme (RAG) pour PHOEBUS.
Permet d'indexer et de rechercher des souvenirs basés sur le contexte sémantique.
"""
import shutil
import time
from datetime import datetime
from pathlib import Path
from PHOEBUS.config import BASE_DIR, GEMINI_API_KEY
from PHOEBUS.memory_backends import sqlite_retrieval

# On importe chromadb de façon optionnelle
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

DB_PATH = str(BASE_DIR / "phoebus_vector_db")

_chroma_client = None
_collection = None
_recovery_attempted = False


def _is_recoverable_chroma_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "database disk image is malformed",
            "rustbindingsapi",
            "object has no attribute 'bindings'",
            "sqlite",
        )
    )


def _backup_corrupt_db() -> Path | None:
    db_path = Path(DB_PATH)
    if not db_path.exists():
        return None
    backup_path = db_path.with_name(f"{db_path.name}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.move(str(db_path), str(backup_path))
    return backup_path

def get_local_embedding_function():
    """Crée une fonction d'embedding locale performante (SentenceTransformer)."""
    try:
        from chromadb.utils import embedding_functions
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception as e:
        print(f"[RAG] Erreur init embedding local : {e}")
    return None

def get_google_embedding_function():
    """Crée une fonction d'embedding utilisant l'API Google Gemini."""
    try:
        from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
        if GEMINI_API_KEY and "votre_clé" not in GEMINI_API_KEY:
            return GoogleGenerativeAiEmbeddingFunction(api_key=GEMINI_API_KEY)
    except Exception as e:
        pass
    return None

def init_chroma():
    global _chroma_client, _collection, _recovery_attempted
    if not CHROMA_AVAILABLE:
        return False
    try:
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=DB_PATH)
            
            # Priorité au local pour la rapidité et éviter les quotas 429
            emb_fn = get_local_embedding_function()
            if not emb_fn:
                emb_fn = get_google_embedding_function()
            
            _collection = _chroma_client.get_or_create_collection(
                name="PHOEBUS_long_term_memory",
                metadata={"hnsw:space": "cosine"},
                embedding_function=emb_fn
            )
        return True
    except Exception as e:
        if not _recovery_attempted and _is_recoverable_chroma_error(e):
            _recovery_attempted = True
            _chroma_client = None
            _collection = None
            try:
                backup_path = _backup_corrupt_db()
                if backup_path:
                    print(f"[RAG] Base ChromaDB corrompue sauvegardée : {backup_path}")
                return init_chroma()
            except Exception as recovery_error:
                print(f"[RAG] Récupération ChromaDB impossible : {recovery_error}")
        print(f"[RAG] Erreur d'initialisation de ChromaDB : {e}")
        return False

def stocker_souvenir(texte: str, source: str = "conversation", importance: int = 1):
    """
    Stocke un événement dans la mémoire à long terme.
    source: 'conversation', 'vision_passive', 'system', etc.
    """
    timestamp = datetime.now().isoformat()
    fallback_ok = sqlite_retrieval.store_memory(
        texte,
        source=source,
        importance=importance,
        timestamp=timestamp,
    )

    if not init_chroma():
        return fallback_ok

    try:
        doc_id = f"mem_{int(time.time() * 1000)}"
        metadata = {
            "source": source,
            "timestamp": timestamp,
            "importance": importance
        }
        
        _collection.add(
            documents=[texte],
            metadatas=[metadata],
            ids=[doc_id]
        )
        return True
    except Exception as e:
        print(f"[RAG] Erreur d'écriture : {e}")
        return fallback_ok

def consolider_souvenirs(max_age_days: int = 30, importance_min: int = 1):
    """Consolidation légère : supprime les souvenirs anciens et peu importants.

    Ce n'est pas encore une vraie consolidation LLM (résumé thématique),
    juste un nettoyage pour éviter que le RAG se dilue. La structure est
    prête à accueillir une version enrichie plus tard.
    """
    if not init_chroma():
        return 0
    try:
        now = datetime.now()
        cutoff = now.timestamp() - max_age_days * 86400
        supprimes = 0
        # ChromaDB n'a pas de filtre par date natif sur tous les backends,
        # on paginera manuellement.
        data = _collection.get(include=["metadatas"])
        ids = data.get("ids", []) or []
        metas = data.get("metadatas", []) or []
        ids_a_virer = []
        for i, meta in enumerate(metas):
            try:
                ts = datetime.fromisoformat(meta.get("timestamp", "")).timestamp()
            except Exception:
                continue
            imp = int(meta.get("importance", 1) or 1)
            if ts < cutoff and imp <= importance_min:
                ids_a_virer.append(ids[i])
        if ids_a_virer:
            _collection.delete(ids=ids_a_virer)
            supprimes = len(ids_a_virer)
        return supprimes
    except Exception as e:
        print(f"[RAG] Erreur consolidation : {e}")
        return 0


def rechercher_souvenirs(requete: str, n_results: int = 3):
    """
    Recherche les souvenirs les plus pertinents par rapport à la requête.
    """
    if not init_chroma():
        return _format_sqlite_results(sqlite_retrieval.search_memory(requete, limit=n_results))

    try:
        results = _collection.query(
            query_texts=[requete],
            n_results=n_results
        )
        
        if not results or not results['documents'] or not results['documents'][0]:
            return _format_sqlite_results(sqlite_retrieval.search_memory(requete, limit=n_results))
            
        souvenirs = []
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i]
            date_str = meta.get('timestamp', '')[:16].replace('T', ' à ')
            src = meta.get('source', 'inconnu')
            souvenirs.append(f"- Le {date_str} (via {src}) : {doc}")
            
        return "\n".join(souvenirs)
    except Exception as e:
        print(f"[RAG] Erreur de recherche : {e}")
        return _format_sqlite_results(sqlite_retrieval.search_memory(requete, limit=n_results))


def _format_sqlite_results(rows):
    souvenirs = []
    for row in rows or []:
        date_str = str(row.get("timestamp", ""))[:16].replace("T", " à ")
        src = row.get("source", "sqlite")
        souvenirs.append(f"- Le {date_str} (via {src}) : {row.get('text', '')}")
    return "\n".join(souvenirs)


def rag_status() -> dict:
    return {
        "chroma_available": CHROMA_AVAILABLE,
        "chroma_ready": bool(_collection is not None),
        "sqlite_fallback": sqlite_retrieval.status(),
    }
