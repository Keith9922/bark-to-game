"""Claude Agent SDK orchestration — writes a self-contained game.html per round.

Flow:
1. Create generated-games/{game_id}/ (short hex).
2. Compose a per-game CLAUDE.md containing the concept, visual recipe (loaded
   by name from visual_recipes/), and the reusable playbook.
3. Spawn claude-agent-sdk with cwd = the game dir and Write-only tool access.
4. Wait for the agent to write game.html (and an optional SUMMARY.md).

Resilience (added in feat/resilient-generation):
- Detect ``RateLimitEvent(status="rejected")`` and fail fast instead of waiting
  for a never-arriving next message — the SDK itself just forwards the event
  and keeps the stream open.
- Per-message watchdog: if no SDK message arrives within ``IDLE_TIMEOUT_S``,
  treat the subprocess as a zombie and abort.
- Publish progress events to the optional ``publish`` callback so the HTTP
  layer can stream them to the browser via SSE.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from bark_to_game.generate import playbook
from bark_to_game.paths import GENERATED_GAMES_DIR, VISUAL_RECIPES_DIR
from bark_to_game.schemas.game import JobEvent

# If the SDK emits no message for this long, treat the subprocess as a zombie.
# Cold-start first-response can take 30-60 s on a fresh /analyze + new Anthropic
# session, so we set the bar generously and rely on RateLimitEvent for fast fail.
IDLE_TIMEOUT_S = 120.0

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


class RateLimitedError(RuntimeError):
    """Raised when the SDK service rejected our request due to rate limits.

    ``resets_at`` is the unix timestamp at which the limit window resets
    (or ``None`` if the SDK did not include one). The HTTP layer surfaces
    this to the browser so the user sees a countdown instead of a timeout.
    """

    def __init__(self, message: str, *, resets_at: int | None) -> None:
        super().__init__(message)
        self.resets_at = resets_at


class GenerationStalledError(RuntimeError):
    """Raised when the SDK subprocess hasn't emitted a message for too long."""


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


def _summarise_message(message: Any) -> str:
    """Short one-liner for SSE event payload (avoid shipping full prompts)."""
    content = getattr(message, "content", None)
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()[:160]
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text.strip()[:160]
    return type(message).__name__


async def _drain(
    generator: Any,
    publish: Callable[[JobEvent], None] | None,
) -> int:
    """Iterate the SDK message stream with rate-limit + watchdog handling.

    Returns the number of Write tool calls observed.

    On any exception (rate-limit, watchdog timeout, or upstream error), the SDK
    generator is explicitly closed so its ``finally`` chain runs and the
    ``claude`` subprocess receives SIGTERM. Without this, calling
    ``iterator.__anext__()`` directly leaves the underlying generator open
    until GC, leaving the subprocess as a zombie.
    """
    # Import inside the function so tests that stub out claude_agent_sdk
    # don't need to provide RateLimitEvent at module import time.
    from claude_agent_sdk import RateLimitEvent

    try:
        return await _drain_inner(generator, publish, RateLimitEvent)
    finally:
        with contextlib.suppress(Exception):
            await generator.aclose()


async def _drain_inner(
    generator: Any,
    publish: Callable[[JobEvent], None] | None,
    rate_limit_event_type: type,
) -> int:
    iterator = generator.__aiter__()
    write_calls = 0
    while True:
        try:
            message = await asyncio.wait_for(iterator.__anext__(), timeout=IDLE_TIMEOUT_S)
        except StopAsyncIteration:
            return write_calls
        except TimeoutError as exc:
            raise GenerationStalledError(
                f"no SDK message for {IDLE_TIMEOUT_S:.0f}s — subprocess likely zombie"
            ) from exc

        if isinstance(message, rate_limit_event_type):
            info = message.rate_limit_info
            if publish:
                publish(
                    JobEvent(
                        type="rate_limit",
                        ts=time.time(),
                        data={
                            "status": info.status,
                            "resets_at": info.resets_at,
                            "rate_limit_type": info.rate_limit_type,
                            "utilization": info.utilization,
                        },
                    )
                )
            if info.status == "rejected":
                raise RateLimitedError(
                    f"Claude service rejected the request (window: {info.rate_limit_type})",
                    resets_at=info.resets_at,
                )
            # "allowed_warning" — keep going; the front-end shows a banner.
            continue

        msg_type = type(message).__name__
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                if getattr(block, "name", None) == "Write":
                    write_calls += 1
                    inp = getattr(block, "input", {}) or {}
                    target = inp.get("file_path") if isinstance(inp, dict) else None
                    logger.info(f"  agent Write → {target}")
                    if publish:
                        publish(
                            JobEvent(
                                type="write",
                                ts=time.time(),
                                data={"file_path": target},
                            )
                        )

        if publish and msg_type in ("AssistantMessage", "UserMessage", "SystemMessage"):
            publish(
                JobEvent(
                    type="message",
                    ts=time.time(),
                    data={"kind": msg_type, "preview": _summarise_message(message)},
                )
            )
        logger.debug(f"  agent message: {msg_type}")


async def generate(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    *,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    """Generate a game.

    ``on_start`` is invoked synchronously with the absolute cwd of the SDK
    subprocess once it's been chosen — used by the HTTP layer to remember the
    cwd so a cancel handler can hard-kill an orphaned subprocess.

    ``publish`` is a non-blocking event sink for the SSE stream. None disables it.
    """
    from claude_agent_sdk import ClaudeAgentOptions, query

    game_id = secrets.token_hex(6)
    game_dir: Path = GENERATED_GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)
    if on_start is not None:
        on_start(str(game_dir))

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
        ),
        publish=publish,
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
