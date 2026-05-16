"""Load and randomly select from the visual recipe pool (markdown files)."""

from __future__ import annotations

import random
from functools import lru_cache
from typing import TypedDict

from bark_to_game.paths import VISUAL_RECIPES_DIR


class VisualRecipe(TypedDict):
    name: str
    markdown: str


@lru_cache(maxsize=1)
def _load_all() -> list[VisualRecipe]:
    out: list[VisualRecipe] = []
    for path in sorted(VISUAL_RECIPES_DIR.glob("recipe_*.md")):
        name = path.stem.removeprefix("recipe_")
        out.append(VisualRecipe(name=name, markdown=path.read_text()))
    if not out:
        raise FileNotFoundError(f"no recipe_*.md found in {VISUAL_RECIPES_DIR}")
    return out


def pick_recipe(seed: int | None = None) -> VisualRecipe:
    rng = random.Random(seed)
    return rng.choice(_load_all())
