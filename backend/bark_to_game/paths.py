"""Resolve paths to repo-root data directories (style cards, recipes, archive)."""

from __future__ import annotations

from pathlib import Path

# backend/bark_to_game/paths.py → repo root is 3 levels up.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

STYLE_CARDS_DIR: Path = REPO_ROOT / "style_cards"
VISUAL_RECIPES_DIR: Path = REPO_ROOT / "visual_recipes"
DATA_DIR: Path = REPO_ROOT / "data"
ARCHIVE_DIR: Path = DATA_DIR / "archive"
