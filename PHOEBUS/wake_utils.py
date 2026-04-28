# PHOEBUS/wake_utils.py
"""Petits helpers de wake word utilisables par la boucle STT et les tests."""

from __future__ import annotations

import re


WAKE_WORDS = (
    "phoebus",
    "phébus",
    "fébus",
    "febus",
    "feubus",
    "foebus",
    "fœbus",
    "phobus",
    "fibus",
    "rebus",
    "hey phoebus",
    "ok phoebus",
    "allo phoebus",
    "salut phoebus",
    "bonjour phoebus",
)

_WAKE_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(w) for w in sorted(WAKE_WORDS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)
_TRIM_RE = re.compile(r"^[\s,;:!?.\-]+|[\s,;:!?.\-]+$")

STOP_CONVERSATION_PHRASES = (
    "laisse tomber",
    "laisse-moi",
    "tais-toi",
    "chut",
    "stop phoebus",
    "merci phoebus",
    "c'est bon phoebus",
)


def has_wake_word(text: str) -> bool:
    """Vrai si la transcription contient PHOEBUS ou une variante STT fréquente."""
    if not text:
        return False
    return bool(_WAKE_RE.search(text))


def strip_wake_word(text: str) -> str:
    """Retire un mot d'appel présent n'importe où dans la phrase."""
    if not text:
        return ""
    cleaned = _WAKE_RE.sub("", text, count=1)
    return _TRIM_RE.sub("", cleaned).strip()


def is_stop_conversation(text: str) -> bool:
    """Commandes naturelles pour fermer la conversation ouverte."""
    text_l = (text or "").lower()
    return any(phrase in text_l for phrase in STOP_CONVERSATION_PHRASES)
