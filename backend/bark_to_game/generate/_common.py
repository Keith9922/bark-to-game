"""Shared types and helpers used by both generator backends."""

from __future__ import annotations

import re
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


class GenerationTruncatedError(RuntimeError):
    """Raised when the model hit its ``max_tokens`` output cap before finishing
    the game, so the ```html block is incomplete. Distinct from a stall: a
    retry with the same cap would truncate again, so the route layer shows a
    specific message and does NOT retry it."""


def load_recipe_markdown(name: str) -> str:
    path = VISUAL_RECIPES_DIR / f"recipe_{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"unknown visual recipe: {name!r}")
    return path.read_text()


def _render_audio_dna(params: dict[str, Any] | None) -> str:
    """Render the audio-derived gameplay knobs as concrete instructions.

    These numbers come from the translate layer's ``_derive_game_params``;
    rendering them in CLAUDE.md gives the generator explicit integers to
    paste into spawn rates / wave timings / random jitter so the same
    mechanic plays differently for different barks.
    """
    if not params:
        return "(no audio DNA — fall back to balanced default pacing)"
    return (
        f"- tempo: **{params['tempo']}** — base spawn / beat interval ≈ "
        f"`{params['spawn_interval_ms']} ms`\n"
        f"- density: **{params['density']}** — cap simultaneous active entities at "
        f"`{params['max_concurrent']}`\n"
        f"- intensity: **{params['intensity']}** — escalate difficulty by "
        f"`×{params['escalation_per_min']:.2f}` per minute\n"
        f"- variability: **{params['variability']}** — apply "
        f"`±{params['randomness_pct']}%` jitter to timings and positions\n"
        f"\n"
        f"USE THESE NUMBERS. Don't guess. The bark IS the pacing."
    )


def _render_rubric(concept: dict[str, Any]) -> str:
    """Render the playability-rubric fields the translate layer produced.

    Each field becomes a concrete acceptance criterion for the generated
    game. Empty strings degrade gracefully — the slot is just omitted.
    """
    bits = []
    onboard = (concept.get("onboarding_hint") or "").strip()
    escalate = (concept.get("escalation_moment") or "").strip()
    replay = (concept.get("replay_hook") or "").strip()
    if onboard:
        bits.append(
            f"- **Zero-read onboarding (seconds 0–3 of play):** {onboard}\n"
            f"  Implement this as a pulsing/glowing visual cue on the first "
            f"interactive element. It MUST fire automatically when play starts."
        )
    if escalate:
        bits.append(
            f"- **Escalation moment:** {escalate}\n"
            f"  Implement this as a visible, named event — flash a brief banner "
            f"(\"WAVE 2!\" / \"SPEED UP\" / etc.) plus an audio sting when it triggers."
        )
    if replay:
        bits.append(
            f"- **Replay hook:** {replay}\n"
            f"  Make this VISIBLE on the fail/win screen so the player understands "
            f"why a second run is worth it."
        )
    if not bits:
        return "(none provided — apply default best practices)"
    return "\n".join(bits)


_MECHANIC_LINE_RE = re.compile(r"- Mechanic:\s*\*\*([\w\-]+)\*\*", re.IGNORECASE)


def _extract_mechanic(style_triplet_summary: str) -> str | None:
    """Pull the mechanic name out of a style-triplet summary block.

    The summary is built in routes/game.py as:
        - Art: **<art>** - ...
        - Mechanic: **<mechanic>** - ...
        - Mood: **<mood>** - ...
    We use the mechanic to slice the playbook so only the relevant code
    sketch lands in CLAUDE.md (keeps generate input stable as the pool grows).
    """
    m = _MECHANIC_LINE_RE.search(style_triplet_summary)
    return m.group(1) if m else None


def build_claude_md(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    game_params: dict[str, Any] | None = None,
) -> str:
    mechanic = _extract_mechanic(style_triplet_summary)
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

## PLAYABILITY REQUIREMENTS (from translate rubric)
{_render_rubric(concept)}

## AUDIO DNA (gameplay knobs derived from THIS bark)
{_render_audio_dna(game_params)}

## STYLE TRIPLET
{style_triplet_summary}

## VISUAL RECIPE (LITERAL — DO NOT DEVIATE)
{load_recipe_markdown(visual_recipe_name)}

## PLAYBOOK (adapt patterns; do not paste verbatim if they clash with the recipe)
{playbook.load_for(mechanic)}

## OUTPUT
- Write the full game to `./game.html` (single self-contained HTML).
- Write a 1-3 line `./SUMMARY.md` describing what you built and how to play.
- Do NOT run any other commands. Do NOT install packages. Only use the Write tool.
"""


def new_game_dir(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    game_params: dict[str, Any] | None = None,
) -> tuple[str, Path, str]:
    """Create the per-game directory, write CLAUDE.md, return (id, dir, spec_text)."""
    game_id = secrets.token_hex(6)
    game_dir = GENERATED_GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)
    claude_md = build_claude_md(concept, style_triplet_summary, visual_recipe_name, game_params)
    (game_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    return game_id, game_dir, claude_md
