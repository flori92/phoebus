"""Façade unifiée sur toutes les couches de mémoire de PHOEBUS.

Les couches sous-jacentes :
- `obsidian.py`    : vault Obsidian indexé dans ChromaDB (notes personnelles).
- `memory.py`        : JSON clé/valeur persistant (préférences factuelles).
- `rag_memory.py`    : ChromaDB vectorielle (souvenirs sémantiques).
- `state.historique` : fenêtre glissante en RAM (tour courant + récents).
- `memory.py` (profil) : compteurs appris (pièces, registre, thèmes).

Cette façade offre une API unique pour que le reste du code n'ait pas à
jongler avec 3 stores différents :

    remember(content, kind="fact", importance=1, key=None)
    recall(query, limit=5)       → liste de résultats unifiés
    note_correction(original, corrected)   → apprentissage auto
    forget_key(key)

Les corrections utilisateur sont stockées dans le RAG avec une importance
haute (3) pour peser plus lourd lors des recherches futures.
"""
import os
from dataclasses import dataclass
from typing import List, Optional

from PHOEBUS.memory import (
    charger_memoire, ajouter_memoire, supprimer_memoire,
    apprendre_signal,
)
from PHOEBUS.rag_memory import stocker_souvenir, rechercher_souvenirs


# Backend : local (JSON+Chroma) ou postgres (multi-device, scalable).
_BACKEND = os.getenv("PHOEBUS_MEMORY_BACKEND", "local").strip().lower()


def _pg():
    """Renvoie le module Postgres s'il est actif et opérationnel, sinon None.
    Permet à memory_unified de router vers Postgres de façon transparente."""
    if _BACKEND != "postgres":
        return None
    try:
        from PHOEBUS.memory_backends import postgres as pg
        if pg.ensure_schema():
            return pg
    except Exception as e:
        print(f"[MEM] Postgres indispo, repli local : {e}")
    return None


@dataclass
class RecallResult:
    source: str  # "fact" | "rag" | "profile"
    text: str
    importance: int = 1
    extra: Optional[dict] = None


def remember(content: str, kind: str = "fact", importance: int = 1,
             key: Optional[str] = None) -> None:
    """Enregistre une information.

    `kind` :
      - "fact"       : préférence explicite clé/valeur (ex: anniversaire).
      - "event"      : événement de vie (va dans le RAG).
      - "correction" : correction d'une réponse (RAG + importance 3).
      - "signal"     : compteur appris (profil) — ex: pièce utilisée.
    """
    if not content:
        return

    # Backend Postgres actif ? Route et sors (sauf signaux profil → local).
    pg = _pg()
    if pg is not None and kind != "signal":
        pg.remember(content, kind=kind, importance=importance, key=key)
        return

    if kind == "fact":
        if key:
            ajouter_memoire(key, content)
        else:
            # Pas de clé explicite : on route vers le RAG.
            stocker_souvenir(content, source="fact", importance=max(importance, 2))
    elif kind == "correction":
        stocker_souvenir(
            "[CORRECTION] " + content,
            source="correction",
            importance=max(importance, 3),
        )
    elif kind == "signal":
        apprendre_signal(content)
    else:  # "event" ou autre
        stocker_souvenir(content, source=kind, importance=importance)


def recall(query: str, limit: int = 5) -> List[RecallResult]:
    """Cherche dans toutes les couches et fusionne les résultats.

    Ordre de priorité :
    1. Faits persistants qui matchent par sous-chaîne (nom exact préféré).
    2. Corrections RAG (forte pondération).
    3. Souvenirs RAG standards.
    """
    # Backend Postgres actif ? La recherche combine faits + vecteurs là-bas.
    pg = _pg()
    if pg is not None:
        items = pg.recall(query, limit=limit)
        return [
            RecallResult(source=r.source, text=r.text, importance=r.importance, extra=r.extra)
            for r in items
        ]

    results: List[RecallResult] = []

    q = (query or "").lower().strip()
    if not q:
        return results

    # ── Faits explicites ───────────────────────────────────────────────────
    facts = charger_memoire()
    for cle, data in facts.items():
        if cle.startswith("_"):
            continue  # champs internes (_profile...)
        if q in cle.lower() or q in str(data.get("valeur", "")).lower():
            results.append(
                RecallResult(
                    source="fact",
                    text=f"{cle} : {data.get('valeur')}",
                    importance=2,
                    extra={"key": cle, "timestamp": data.get("timestamp")},
                )
            )

    # ── RAG (corrections + standards, déjà ordonnés par similarité) ───────
    rag_text = rechercher_souvenirs(query, n_results=limit)
    if rag_text:
        for line in rag_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            is_correction = "[CORRECTION]" in line or "(via correction)" in line
            results.append(
                RecallResult(
                    source="rag",
                    text=line,
                    importance=3 if is_correction else 1,
                )
            )

    # ── Obsidian vault (notes personnelles indexées dans ChromaDB) ─────────
    try:
        from PHOEBUS.obsidian import OBSIDIAN_ENABLED, search_vault_semantic
        if OBSIDIAN_ENABLED:
            import asyncio
            import threading

            async def _search():
                return await search_vault_semantic(q, n_results=min(limit, 3))

            try:
                asyncio.get_running_loop()
                has_running_loop = True
            except RuntimeError:
                has_running_loop = False

            if has_running_loop:
                holder = {"hits": [], "error": None}

                def _runner():
                    try:
                        holder["hits"] = asyncio.run(_search())
                    except Exception as exc:
                        holder["error"] = exc

                thread = threading.Thread(target=_runner, daemon=True)
                thread.start()
                thread.join(timeout=8)
                if thread.is_alive():
                    vault_hits = []
                elif holder["error"] is not None:
                    raise holder["error"]
                else:
                    vault_hits = holder["hits"]
            else:
                vault_hits = asyncio.run(_search())
            for hit in (vault_hits or []):
                snippet = hit.get("text", "")[:300]
                fname = hit.get("file", "?")
                score = hit.get("score", 0)
                if score > 0.3:  # Seuil de pertinence minimale
                    results.append(
                        RecallResult(
                            source="obsidian",
                            text=f"[Note: {fname}] {snippet}",
                            importance=2 if score > 0.6 else 1,
                            extra={"file": fname, "score": score},
                        )
                    )
    except Exception as e:
        pass  # Obsidian non configuré ou erreur, on ignore silencieusement

    # Tri global : importance décroissante.
    results.sort(key=lambda r: -r.importance)
    return results[:limit]


def forget_key(key: str) -> bool:
    pg = _pg()
    if pg is not None:
        return pg.forget_key(key)
    return supprimer_memoire(key)


def note_correction(original: str, corrected: str) -> None:
    """Capture une correction utilisateur.

    Exemple : PHOEBUS a dit "il fait 25°C à Paris" → utilisateur répond
    "non, je voulais Lyon". On enregistre la correction pour que les
    futurs prompts aient accès à ce signal.
    """
    payload = (
        f"Floriace a corrigé une réponse précédente. "
        f"Réponse initiale de PHOEBUS : « {original.strip()[:250]} ». "
        f"Correction de Floriace : « {corrected.strip()[:250]} ». "
        f"PHOEBUS doit retenir la correction et s'y conformer."
    )
    remember(payload, kind="correction", importance=3)


# ── Détection automatique de correction dans le fil de parole ────────────

_CORRECTION_TRIGGERS = (
    "non, ", "non pas ", "plutôt ", "en fait ",
    "pas comme ça", "pas ça", "tu as tort", "tu te trompes",
    "ce n'est pas ça", "c'est pas ça", "ce n'est pas ce que",
    "j'ai dit ", "je voulais dire ", "je parlais de ",
    "corrige", "rectifie",
)


def looks_like_correction(user_text: str) -> bool:
    """Heuristique : la phrase utilisateur ressemble-t-elle à une correction ?"""
    if not user_text:
        return False
    t = user_text.lower().strip()
    return any(trig in t for trig in _CORRECTION_TRIGGERS)
