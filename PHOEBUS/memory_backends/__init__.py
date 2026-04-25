"""Backends de stockage de la mémoire Jarvis.

L'API unifiée est dans `jarvis.memory_unified`. Ce package fournit des
implémentations alternatives (Postgres, future SQLite...) activables via
l'environnement.

    PHOEBUS_MEMORY_BACKEND=local     (défaut : JSON + ChromaDB local)
    PHOEBUS_MEMORY_BACKEND=postgres  (nécessite DATABASE_URL et pip install)
"""
