"""Façade unifiée sur toutes les couches de mémoire de PHOEBUS.

Les couches sous-jacentes :
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
from dataclasses import dataclass
from typing import List, Optional

from PHOEBUS.memory import (
    charger_memoire, ajouter_memoire, supprimer_memoire,
    apprendre_signal,
)
from PHOEBUS.rag_memory import stocker_souvenir, rechercher_souvenirs


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

    # Tri global : importance décroissante.
    results.sort(key=lambda r: -r.importance)
    return results[:limit]


def forget_key(key: str) -> bool:
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
