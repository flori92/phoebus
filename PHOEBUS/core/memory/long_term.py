# phoebus/core/memory/long_term.py
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import os

class LongTermMemory:
    def __init__(self, persist_dir: str = None):
        if persist_dir is None:
            # On utilise le dossier data/ de la nouvelle structure
            from PHOEBUS.config import BASE_DIR
            persist_dir = os.path.join(BASE_DIR, "data", "memory")
        
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Modèle d'embedding local et performant
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Collections spécialisées
        self.conversations = self.client.get_or_create_collection(
            "conversations", embedding_function=self.ef
        )
        self.facts = self.client.get_or_create_collection(
            "facts_about_user", embedding_function=self.ef
        )
        self.actions = self.client.get_or_create_collection(
            "actions_history", embedding_function=self.ef
        )
        self.preferences = self.client.get_or_create_collection(
            "user_preferences", embedding_function=self.ef
        )
    
    def remember_conversation(self, user_msg: str, assistant_msg: str):
        """Stocke un échange dans la mémoire vectorielle"""
        ts = datetime.now()
        self.conversations.add(
            documents=[f"User: {user_msg}\nPhoebus: {assistant_msg}"],
            metadatas=[{
                "timestamp": ts.isoformat(),
                "type": "conversation"
            }],
            ids=[f"conv_{ts.timestamp()}"]
        )
    
    def learn_fact(self, fact: str, category: str = "general"):
        """Apprend un fait sur Floriace"""
        ts = datetime.now()
        self.facts.add(
            documents=[fact],
            metadatas=[{
                "timestamp": ts.isoformat(),
                "category": category
            }],
            ids=[f"fact_{ts.timestamp()}"]
        )
    
    def search(self, query: str, collection: str = "all", top_k: int = 5) -> list:
        """Recherche dans les différentes mémoires"""
        results = []
        
        collections = {
            "conversations": self.conversations,
            "facts": self.facts,
            "actions": self.actions,
            "preferences": self.preferences
        }
        
        if collection == "all":
            for name, coll in collections.items():
                if coll.count() > 0:
                    r = coll.query(query_texts=[query], n_results=min(top_k, coll.count()))
                    results.extend(r["documents"][0] if r["documents"] else [])
        else:
            coll = collections.get(collection)
            if coll and coll.count() > 0:
                r = coll.query(query_texts=[query], n_results=min(top_k, coll.count()))
                results = r["documents"][0] if r["documents"] else []
        
        return results
