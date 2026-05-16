"""YAMNet wrapper — lazy load of the TF Hub model, dog-class scoring.

YAMNet ships a 521-class AudioSet classifier. We only care about the
dog-related classes (Bark, Yip, Howl, Bow-wow, Growling, Whimper, Dog) and
collapse the result into our token vocabulary.

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
    "Dog": "BARK",  # generic dog → BARK
    "Bark": "BARK",
    "Yip": "YIP",
    "Howl": "HOWL",
    "Bow-wow": "BARK",
    "Growling": "GROWL",
    "Whimper (dog)": "WHIMPER",
}


class Classification(TypedDict):
    type: str
    confidence: float
    raw_scores: dict[str, float]


@lru_cache(maxsize=1)
def _load_model() -> Any:
    # Set legacy Keras flag before importing tensorflow_hub (YAMNet was built
    # against Keras 2; the bundled tf-keras package provides the legacy API).
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    import tensorflow_hub as hub  # type: ignore[import-untyped]

    return hub.load("https://tfhub.dev/google/yamnet/1")


@lru_cache(maxsize=1)
def _load_dog_indices() -> dict[str, int]:
    model = _load_model()
    class_map_path: str = model.class_map_path().numpy().decode("utf-8")
    with open(class_map_path, newline="") as f:
        reader = csv.DictReader(f)
        indices = {row["display_name"]: i for i, row in enumerate(reader)}
    return {n: indices[n] for n in DOG_CLASS_NAMES if n in indices}


def classify(y: np.ndarray, sr: int) -> Classification:
    """Run YAMNet and pick the strongest dog-related class."""
    if sr != 16000:
        raise ValueError(f"YAMNet requires 16 kHz audio, got {sr}")
    if y.size == 0:
        raise ValueError("Empty audio buffer")

    model = _load_model()
    dog_indices = _load_dog_indices()
    if not dog_indices:
        raise RuntimeError("YAMNet class map missing dog classes")

    scores_tensor, _, _ = model(y.astype(np.float32))
    mean_scores = scores_tensor.numpy().mean(axis=0)

    dog_scores = {name: float(mean_scores[idx]) for name, idx in dog_indices.items()}
    top_display = max(dog_scores, key=lambda k: dog_scores[k])
    return Classification(
        type=DISPLAY_TO_TOKEN[top_display],
        confidence=dog_scores[top_display],
        raw_scores=dog_scores,
    )
