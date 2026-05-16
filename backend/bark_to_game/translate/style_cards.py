"""Load and randomly select from the art / mechanic / mood card pools."""

from __future__ import annotations

import json
import random
from functools import lru_cache
from typing import TypedDict, cast

from bark_to_game.paths import STYLE_CARDS_DIR


class ArtStyle(TypedDict):
    name: str
    description: str
    palette_hint: str


class Mechanic(TypedDict):
    name: str
    description: str
    input: str


class Mood(TypedDict):
    name: str
    description: str


class StyleTriplet(TypedDict):
    art: ArtStyle
    mechanic: Mechanic
    mood: Mood


@lru_cache(maxsize=1)
def _load_art() -> list[ArtStyle]:
    return cast(list[ArtStyle], json.loads((STYLE_CARDS_DIR / "art_styles.json").read_text()))


@lru_cache(maxsize=1)
def _load_mechanics() -> list[Mechanic]:
    return cast(list[Mechanic], json.loads((STYLE_CARDS_DIR / "mechanics.json").read_text()))


@lru_cache(maxsize=1)
def _load_moods() -> list[Mood]:
    return cast(list[Mood], json.loads((STYLE_CARDS_DIR / "moods.json").read_text()))


def pick_triplet(seed: int | None = None) -> StyleTriplet:
    """Randomly pick one card from each pool. If `seed` is provided, the
    pick is deterministic (per the audio_hash seed pattern)."""
    rng = random.Random(seed)
    return StyleTriplet(
        art=rng.choice(_load_art()),
        mechanic=rng.choice(_load_mechanics()),
        mood=rng.choice(_load_moods()),
    )
