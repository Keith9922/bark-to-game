"""Load and randomly select from the art / mechanic / mood card pools.

Picking strategy:
- Deterministic seed (audio_hash prefix) → reproducible without diversity input.
- Optional ``occupied_cells`` set down-weights triplets that were already
  generated for this session. Each axis (art / mechanic / mood) that overlaps
  with an occupied cell takes a soft penalty — the cell isn't forbidden, just
  less likely. So a fresh session has uniform odds; after 8 generations,
  unused (art, mechanic, mood) combinations dominate the next pick.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from typing import TypedDict, cast

from bark_to_game.paths import STYLE_CARDS_DIR

# How much each axis-overlap with the occupied cell set discounts a card's
# weight. 0.5 means a card whose name appears in every prior cell is half as
# likely to be picked — soft, not hard.
_AXIS_OVERLAP_PENALTY = 0.5


class ArtStyle(TypedDict):
    name: str
    description: str
    palette_hint: str


class Mechanic(TypedDict):
    name: str
    description: str
    input: str
    core_loop: str


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


def _weighted_pick(
    rng: random.Random,
    cards: list[dict[str, object]],
    used_names: set[str],
) -> dict[str, object]:
    """Pick one card biased away from names already used in the session."""
    weights = [
        _AXIS_OVERLAP_PENALTY if card["name"] in used_names else 1.0
        for card in cards
    ]
    return rng.choices(cards, weights=weights, k=1)[0]


def pick_triplet(
    seed: int | None = None,
    occupied_cells: set[tuple[str, str, str]] | None = None,
) -> StyleTriplet:
    """Pick one (art, mechanic, mood) triplet.

    With ``seed``, the pick is deterministic per audio_hash. ``occupied_cells``
    (the set of triplets already generated in this session) softly down-weights
    cards whose name already appears on any prior axis so a session of 8
    generations naturally explores 24 distinct cards rather than re-rolling
    the same handful.
    """
    rng = random.Random(seed)
    if not occupied_cells:
        return StyleTriplet(
            art=rng.choice(_load_art()),
            mechanic=rng.choice(_load_mechanics()),
            mood=rng.choice(_load_moods()),
        )

    used_art = {cell[0] for cell in occupied_cells}
    used_mech = {cell[1] for cell in occupied_cells}
    used_mood = {cell[2] for cell in occupied_cells}

    return StyleTriplet(
        art=cast(ArtStyle, _weighted_pick(rng, cast(list[dict[str, object]], _load_art()), used_art)),
        mechanic=cast(
            Mechanic, _weighted_pick(rng, cast(list[dict[str, object]], _load_mechanics()), used_mech)
        ),
        mood=cast(Mood, _weighted_pick(rng, cast(list[dict[str, object]], _load_moods()), used_mood)),
    )
