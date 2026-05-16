"""Loader for the game-assets playbook (markdown that Claude adapts patterns from)."""

from __future__ import annotations

from functools import lru_cache

from bark_to_game.paths import GAME_ASSETS_DIR


@lru_cache(maxsize=1)
def load() -> str:
    return (GAME_ASSETS_DIR / "playbook.md").read_text()
