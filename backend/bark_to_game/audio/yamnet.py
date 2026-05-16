"""YAMNet wrapper — lazy load of the TF Hub model, strict dog detection.

YAMNet ships a 521-class AudioSet classifier. We collapse the dog-related
classes (Bark, Yip, Howl, Bow-wow, Growling, Whimper, Dog) into our token
vocabulary AND compare them against the global top class so we can reject
audio that isn't actually dog-like (Speech, Music, Ambient noise, etc.).

The model is loaded on first use and memoised. If TF / Hub is unavailable the
caller catches the exception and falls back to a heuristic.
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import Any, TypedDict

import numpy as np

DOG_CLASS_NAMES: tuple[str, ...] = (
    "Dog",
    "Bark",
    "Yip",
    "Howl",
    "Bow-wow",
    "Growling",
    "Whimper (dog)",
)

# Map YAMNet display names to our short token vocabulary.
DISPLAY_TO_TOKEN: dict[str, str] = {
    "Dog": "BARK",  # generic dog -> BARK
    "Bark": "BARK",
    "Yip": "YIP",
    "Howl": "HOWL",
    "Bow-wow": "BARK",
    "Growling": "GROWL",
    "Whimper (dog)": "WHIMPER",
}

# Minimum dog-class score for a segment to count as "dog-like". Human imitation
# of barks scores lower than real dog audio, so we set the bar permissively.
DOG_SCORE_MIN: float = 0.04

# If the absolute top YAMNet class is in this set, we treat the segment as
# definitely not dog-like — even a small dog-score is noise. Captures the
# common "talking into the mic" case the demo would otherwise classify as BARK.
NON_DOG_DOMINANT_CLASSES: frozenset[str] = frozenset(
    {
        # Human voice
        "Speech",
        "Conversation",
        "Narration, monologue",
        # Music
        "Music",
        "Musical instrument",
        "Singing",
        # Silence / electronics / ambient noise. Note we deliberately do NOT
        # include "Inside, small room" / "Echo" — real bark recordings often
        # co-occur with those, rejecting them would false-negative valid input.
        "Silence",
        "White noise",
        "Pink noise",
        "Hum",
        "Mains hum",
        "Static",
        "Wind",
        "Busy signal",  # synthesised test fixtures land here
    }
)


class Classification(TypedDict):
    type: str
    confidence: float
    raw_scores: dict[str, float]
    is_dog_like: bool
    top_other_class: str
    top_other_score: float


@lru_cache(maxsize=1)
def _load_model() -> Any:
    # Set legacy Keras flag before importing tensorflow_hub (YAMNet was built
    # against Keras 2; the bundled tf-keras package provides the legacy API).
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    import tensorflow_hub as hub  # type: ignore[import-untyped]

    return hub.load("https://tfhub.dev/google/yamnet/1")


@lru_cache(maxsize=1)
def _load_class_map() -> list[str]:
    """All 521 YAMNet class display names in index order."""
    model = _load_model()
    class_map_path: str = model.class_map_path().numpy().decode("utf-8")
    with open(class_map_path, newline="") as f:
        reader = csv.DictReader(f)
        return [row["display_name"] for row in reader]


@lru_cache(maxsize=1)
def _load_dog_indices() -> dict[str, int]:
    names = _load_class_map()
    by_name = {name: i for i, name in enumerate(names)}
    return {n: by_name[n] for n in DOG_CLASS_NAMES if n in by_name}


def _decide_dog_like(
    top_dog_score: float, top_other_class: str, top_other_score: float
) -> bool:
    """Two-rule judgement:

    1. The dog score must clear the minimum confidence floor (``DOG_SCORE_MIN``).
    2. If the globally-top class is in ``NON_DOG_DOMINANT_CLASSES`` AND
       outscores the top dog class by more than 2x, reject — the audio is
       overwhelmingly something else.

    Rule 2 catches the "person talking into the mic" case where Speech
    scores 0.9 and Bark scores 0.05.
    """
    if top_dog_score < DOG_SCORE_MIN:
        return False
    return not (
        top_other_class in NON_DOG_DOMINANT_CLASSES
        and top_other_score > 2.0 * top_dog_score
    )


def classify(y: np.ndarray, sr: int) -> Classification:
    """Run YAMNet, pick the strongest dog-related class, and judge dog-likeness."""
    if sr != 16000:
        raise ValueError(f"YAMNet requires 16 kHz audio, got {sr}")
    if y.size == 0:
        raise ValueError("Empty audio buffer")

    model = _load_model()
    class_names = _load_class_map()
    dog_indices = _load_dog_indices()
    if not dog_indices:
        raise RuntimeError("YAMNet class map missing dog classes")

    scores_tensor, _, _ = model(y.astype(np.float32))
    mean_scores = scores_tensor.numpy().mean(axis=0)

    dog_scores = {name: float(mean_scores[idx]) for name, idx in dog_indices.items()}
    top_display = max(dog_scores, key=lambda k: dog_scores[k])
    top_dog_score = dog_scores[top_display]

    # Top non-dog class across all 521.
    dog_idx_set = set(dog_indices.values())
    best_other_idx = -1
    best_other_score = -1.0
    for i, s in enumerate(mean_scores):
        if i in dog_idx_set:
            continue
        if s > best_other_score:
            best_other_score = float(s)
            best_other_idx = i
    top_other_class = class_names[best_other_idx] if best_other_idx >= 0 else ""

    return Classification(
        type=DISPLAY_TO_TOKEN[top_display],
        confidence=top_dog_score,
        raw_scores=dog_scores,
        is_dog_like=_decide_dog_like(top_dog_score, top_other_class, best_other_score),
        top_other_class=top_other_class,
        top_other_score=best_other_score,
    )
