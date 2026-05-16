"""Claude Agent SDK orchestration — writes a self-contained game.html per round.

Flow:
1. Create generated-games/{game_id}/ (short hex).
2. Compose a per-game CLAUDE.md containing the concept, visual recipe (loaded
   by name from visual_recipes/), and the reusable playbook.
3. Spawn claude-agent-sdk with cwd = the game dir and Write-only tool access.
4. Wait for the agent to write game.html (and an optional SUMMARY.md).
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from bark_to_game.generate import playbook
from bark_to_game.paths import GENERATED_GAMES_DIR, VISUAL_RECIPES_DIR

SYSTEM_PROMPT = """\
You are an expert HTML5/Canvas game developer.

Your job: read ./CLAUDE.md in the current directory, then write a single
self-contained ./game.html implementing the game concept exactly. Also write a
short ./SUMMARY.md describing what you built (1-3 lines).

Non-negotiable constraints:
1. ONE self-contained game.html. All <style> and <script> inline.
2. No external CDNs, no external libraries, no module imports.
3. Canvas 2D only (no WebGL, no SVG).
4. Web Audio API for sound — synthesise, no audio files.
5. Input: WASD/arrow keys + click/touch. Must work on mobile (touch + responsive).
6. Implement: title screen → gameplay → win/lose state → restart on click/tap/Enter.
7. Follow the VISUAL RECIPE in CLAUDE.md literally: palette hex codes,
   typography, motion vocabulary, audio cues, DO-NOTs. Do not deviate.
8. Adapt patterns from the PLAYBOOK section — do not paste verbatim if they
   conflict with the recipe.
9. Playable round must complete in ~30 s and be clearly winnable / losable.

Use Write tool. Do not use Bash, Read, or Edit.
"""


class GenerationResult(TypedDict):
    game_id: str
    game_path: str  # absolute path
    summary: str
    cwd: str


def _build_claude_md(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_md: str,
    playbook_md: str,
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
{visual_recipe_md}

## PLAYBOOK (adapt patterns; do not paste verbatim if they clash with the recipe)
{playbook_md}

## OUTPUT
- Write the full game to `./game.html` (single self-contained HTML).
- Write a 1-3 line `./SUMMARY.md` describing what you built and how to play.
- Do NOT run any other commands. Do NOT install packages. Only use the Write tool.
"""


def _load_recipe_markdown(name: str) -> str:
    path = VISUAL_RECIPES_DIR / f"recipe_{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"unknown visual recipe: {name!r}")
    return path.read_text()


async def _drain(generator: Any) -> int:
    """Iterate the SDK message stream, counting and logging tool calls."""
    write_calls = 0
    async for message in generator:
        # Log the message kind for diagnostics (best-effort, schema-agnostic).
        msg_type = type(message).__name__
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                tool = getattr(block, "name", None)
                if tool == "Write":
                    write_calls += 1
                    inp = getattr(block, "input", {}) or {}
                    target = inp.get("file_path") if isinstance(inp, dict) else None
                    logger.info(f"  agent Write → {target}")
        logger.debug(f"  agent message: {msg_type}")
    return write_calls


async def generate(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
) -> GenerationResult:
    from claude_agent_sdk import ClaudeAgentOptions, query

    game_id = secrets.token_hex(6)
    game_dir: Path = GENERATED_GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    recipe_md = _load_recipe_markdown(visual_recipe_name)
    claude_md = _build_claude_md(
        concept=concept,
        style_triplet_summary=style_triplet_summary,
        visual_recipe_md=recipe_md,
        playbook_md=playbook.load(),
    )
    (game_dir / "CLAUDE.md").write_text(claude_md)

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Write"],
        permission_mode="bypassPermissions",
        cwd=str(game_dir),
        max_turns=8,
    )

    logger.info(f"generate: game_id={game_id} cwd={game_dir} recipe={visual_recipe_name}")
    write_calls = await _drain(
        query(
            prompt=(
                "Read ./CLAUDE.md, then implement the game described there.\n"
                "Write the full HTML to ./game.html and a 1-3 line ./SUMMARY.md.\n"
                "Use only the Write tool."
            ),
            options=options,
        )
    )
    logger.info(f"generate: game_id={game_id} writes={write_calls}")

    game_path = game_dir / "game.html"
    if not game_path.exists():
        raise RuntimeError(f"agent did not produce game.html for {game_id} (writes={write_calls})")

    summary_path = game_dir / "SUMMARY.md"
    summary = summary_path.read_text().strip() if summary_path.exists() else "(no summary)"

    return GenerationResult(
        game_id=game_id,
        game_path=str(game_path),
        summary=summary,
        cwd=str(game_dir),
    )
