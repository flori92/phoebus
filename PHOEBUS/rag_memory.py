# PHOEBUS/rag_memory.py
"""
Mémoire Vectorielle Long Terme (RAG) pour PHOEBUS.
Permet d'indexer et de rechercher des souvenirs basés sur le contexte sémantique.
"""
import os
import time
from datetime import datetime
from PHOEBUS.config import BASE_DIR, GEMINI_API_KEY

# On importe chromadb de façon optionnelle
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

DB_PATH = str(BASE_DIR / "phoebus_vector_db")

_chroma_client = None
_collection = None

def get_google_embedding_function():
    """Crée une fonction d'embedding utilisant l'API Google Gemini."""
    try:
        import google.generativeai as genai
        from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
        if GEMINI_API_KEY and "votre_clé" not in GEMINI_API_KEY:
            return GoogleGenerativeAiEmbeddingFunction(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"[RAG] Impossible d'initialiser les Google Embeddings, repli sur local : {e}")
    return None

def init_chroma():
    global _chroma_client, _collection
    if not CHROMA_AVAILABLE:
        return False
    try:
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=DB_PATH)
            
            emb_fn = get_google_embedding_function()
            
            _collection = _chroma_client.get_or_create_collection(
                name="PHOEBUS_long_term_memory",
                metadata={"hnsw:space": "cosine"},
                embedding_function=emb_fn
            )
        return True
    except Exception as e:
        print(f"[RAG] Erreur d'initialisation de ChromaDB : {e}")
        return False

def stocker_souvenir(texte: str, source: str = "conversation", importance: int = 1):
    """
    Stocke un événement dans la mémoire à long terme.
    source: 'conversation', 'vision_passive', 'system', etc.
    """
    if not init_chroma():
        return False
    
    try:
        doc_id = f"mem_{int(time.time() * 1000)}"
        timestamp = datetime.now().isoformat()
        
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
        return False

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
        return ""
        
    try:
        results = _collection.query(
            query_texts=[requete],
            n_results=n_results
        )
        
        if not results or not results['documents'] or not results['documents'][0]:
            return ""
            
        souvenirs = []
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i]
            date_str = meta.get('timestamp', '')[:16].replace('T', ' à ')
            src = meta.get('source', 'inconnu')
            souvenirs.append(f"- Le {date_str} (via {src}) : {doc}")
            
        return "\n".join(souvenirs)
    except Exception as e:
        print(f"[RAG] Erreur de recherche : {e}")
        return ""
