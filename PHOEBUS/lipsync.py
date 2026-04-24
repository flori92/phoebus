"""Helpers de lipsync pour le visage de PHOEBUS.

Le backend TTS ne fournit pas toujours des visèmes natifs. Quand un moteur
expose des repères temporels de mots (comme edge-tts), on répartit ensuite
des groupes phonétiques français dans ces fenêtres temporelles pour obtenir
un rendu bouche plus crédible et mieux synchronisé.
"""

from __future__ import annotations

import re
from typing import Iterable

PHONEME_CLUSTERS = (
    "eaux",
    "eau",
    "oin",
    "ion",
    "ain",
    "ein",
    "ien",
    "ou",
    "on",
    "an",
    "en",
    "in",
    "ai",
    "ei",
    "au",
    "eu",
    "oeu",
    "oe",
    "oi",
    "ui",
    "ch",
    "gn",
    "ph",
)


def clean_speech_text(text: str) -> str:
    return str(text or "").replace("{", " {").replace("}", "} ").strip()


def normalize_speech(text: str) -> str:
    try:
        normalized = clean_speech_text(text).lower()
        import unicodedata

        normalized = unicodedata.normalize("NFD", normalized)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return normalized
    except Exception:
        return clean_speech_text(text).lower()


def tokenize_word(word: str) -> list[str]:
    normalized = normalize_speech(word)
    fragments = re.findall(r"[a-z]+", normalized)
    tokens: list[str] = []

    for fragment in fragments:
        index = 0
        while index < len(fragment):
            cluster = next(
                (item for item in PHONEME_CLUSTERS if fragment.startswith(item, index)),
                None,
            )
            if cluster:
                tokens.append(cluster)
                index += len(cluster)
            else:
                tokens.append(fragment[index])
                index += 1
    return tokens


def viseme_for_token(token: str) -> dict[str, float]:
    if re.fullmatch(r"[mbp]", token):
        return {"open": 0.0, "width": 0.98, "skew": 0.0, "lift": 0.02}
    if token in {"f", "v", "ph"}:
        return {"open": 0.12, "width": 1.01, "skew": 0.02, "lift": 0.01}
    if token in {"ou", "o", "on", "au", "eu", "u"}:
        return {"open": 0.24, "width": 0.88, "skew": 0.0, "lift": 0.0}
    if token in {"a", "an", "en", "eau", "ain", "ein"}:
        return {"open": 0.36, "width": 1.14, "skew": 0.0, "lift": 0.02}
    if token in {"e", "i", "y", "ai", "ei", "ui", "ien", "oi"}:
        return {"open": 0.2, "width": 1.12, "skew": 0.02, "lift": 0.05}
    return {"open": 0.16, "width": 1.02, "skew": 0.0, "lift": 0.0}


def token_weight(token: str) -> float:
    if re.fullmatch(r"[mbp]", token):
        return 0.6
    if token in {"f", "v", "ph"}:
        return 0.9
    if token in {"ou", "o", "on", "au", "eu", "u"}:
        return 1.35
    if token in {"a", "an", "en", "eau", "ain", "ein"}:
        return 1.45
    if token in {"e", "i", "y", "ai", "ei", "ui", "ien", "oi"}:
        return 1.1
    return 0.95


def _rest_frame(start_ms: float, duration_ms: float) -> dict[str, float]:
    return {
        "time_ms": round(start_ms, 1),
        "duration_ms": round(duration_ms, 1),
        "open": 0.03,
        "width": 1.0,
        "skew": 0.0,
        "lift": 0.0,
    }


def build_lipsync_frames_from_word_boundaries(
    boundaries: Iterable[dict[str, object]],
) -> list[dict[str, float]]:
    frames: list[dict[str, float]] = []
    prev_end_ms = 0.0

    normalized_boundaries = sorted(
        (
            {
                "offset_ms": max(0.0, float(item.get("offset_ms", 0.0))),
                "duration_ms": max(45.0, float(item.get("duration_ms", 0.0))),
                "text": str(item.get("text", "") or ""),
            }
            for item in boundaries
        ),
        key=lambda item: item["offset_ms"],
    )

    for boundary in normalized_boundaries:
        start_ms = boundary["offset_ms"]
        duration_ms = boundary["duration_ms"]
        text = boundary["text"]
        tokens = tokenize_word(text)
        if not tokens:
            continue

        gap_ms = start_ms - prev_end_ms
        if gap_ms > 40:
            frames.append(_rest_frame(prev_end_ms, min(gap_ms, 140)))

        weights = [token_weight(token) for token in tokens]
        total_weight = sum(weights) or float(len(tokens))
        cursor_ms = start_ms
        boundary_end_ms = start_ms + duration_ms

        for index, token in enumerate(tokens):
            slice_ms = max(36.0, duration_ms * (weights[index] / total_weight))
            if index == len(tokens) - 1:
                slice_ms = max(36.0, boundary_end_ms - cursor_ms)
            viseme = viseme_for_token(token)
            frames.append(
                {
                    "time_ms": round(cursor_ms, 1),
                    "duration_ms": round(slice_ms, 1),
                    "open": viseme["open"],
                    "width": viseme["width"],
                    "skew": viseme["skew"],
                    "lift": viseme["lift"],
                }
            )
            cursor_ms += slice_ms

        prev_end_ms = max(prev_end_ms, boundary_end_ms)

    if frames:
        last_end_ms = frames[-1]["time_ms"] + frames[-1]["duration_ms"]
        frames.append(_rest_frame(last_end_ms, 90.0))

    return frames
