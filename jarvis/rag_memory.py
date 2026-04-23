# jarvis/rag_memory.py
"""
Mémoire Vectorielle Long Terme (RAG) pour JARVIS.
Permet d'indexer et de rechercher des souvenirs basés sur le contexte sémantique.
"""
import os
import time
from datetime import datetime
from jarvis.config import BASE_DIR

# On importe chromadb de façon optionnelle pour ne pas casser le système s'il n'est pas installé
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

DB_PATH = str(BASE_DIR / "jarvis_vector_db")

_chroma_client = None
_collection = None

def init_chroma():
    global _chroma_client, _collection
    if not CHROMA_AVAILABLE:
        return False
    try:
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=DB_PATH)
            _collection = _chroma_client.get_or_create_collection(
                name="jarvis_long_term_memory",
                metadata={"hnsw:space": "cosine"}
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
