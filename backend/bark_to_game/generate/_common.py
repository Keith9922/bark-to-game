"""Shared types and helpers used by both generator backends."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, TypedDict

from bark_to_game.generate import playbook
from bark_to_game.paths import GENERATED_GAMES_DIR, VISUAL_RECIPES_DIR


class GenerationResult(TypedDict):
    game_id: str
    game_path: str  # absolute path to game.html
    summary: str
    cwd: str  # absolute path to the per-game dir


class RateLimitedError(RuntimeError):
    """Raised when the upstream service rejected the request due to rate limits.

    ``resets_at`` is the unix timestamp at which the limit window resets
    (or ``None`` if the upstream did not include one). The HTTP layer
    surfaces this to the browser so the user sees a countdown.
    """

    def __init__(self, message: str, *, resets_at: int | None) -> None:
        super().__init__(message)
        self.resets_at = resets_at


class GenerationStalledError(RuntimeError):
    """Raised when the upstream stops emitting progress for too long."""


def load_recipe_markdown(name: str) -> str:
    path = VISUAL_RECIPES_DIR / f"recipe_{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"unknown visual recipe: {name!r}")
    return path.read_text()


def build_claude_md(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
) -> str:
    return f"""\
# Game generation spec

You must produce a single playable HTML5/Canvas game.

## CONCEPT
**{concept["title"]}** — {concept["tagline"]}

- Player: {concept["player"]}
- Core mechanic: {concept["core_mechanic"]}
- Win condition: {concept["win_condition"]}
- Fail condition: {concept["fail_condition"]}
- Visual summary: {concept["visual_summary"]}
- Audio summary: {concept["audio_summary"]}

## STYLE TRIPLET
{style_triplet_summary}

## VISUAL RECIPE (LITERAL — DO NOT DEVIATE)
{load_recipe_markdown(visual_recipe_name)}

## PLAYBOOK (adapt patterns; do not paste verbatim if they clash with the recipe)
{playbook.load()}

## OUTPUT
- Write the full game to `./game.html` (single self-contained HTML).
- Write a 1-3 line `./SUMMARY.md` describing what you built and how to play.
- Do NOT run any other commands. Do NOT install packages. Only use the Write tool.
"""


def new_game_dir(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
) -> tuple[str, Path, str]:
    """Create the per-game directory, write CLAUDE.md, return (id, dir, spec_text)."""
    game_id = secrets.token_hex(6)
    game_dir = GENERATED_GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)
    claude_md = build_claude_md(concept, style_triplet_summary, visual_recipe_name)
    (game_dir / "CLAUDE.md").write_text(claude_md)
    return game_id, game_dir, claude_md
