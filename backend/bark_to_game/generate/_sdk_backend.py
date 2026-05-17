"""Generation via the local claude-agent-sdk subprocess.

Shares the SDK process with the user's Claude Code window — both consume the
same Claude Max plan quota. When the user is actively working in Claude Code
the service rate-limits this path silently; the watchdog + RateLimitEvent
detection in :func:`_drain` are what surface that failure quickly.

This module is the legacy backend; the API backend (``_api_backend.py``) is
the default and the one the user-facing flow exercises now. Keeping this
backend means a ``BARK_GENERATOR_MODE=sdk`` deployment still works as before.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from bark_to_game.generate._common import (
    GenerationResult,
    GenerationStalledError,
    RateLimitedError,
    new_game_dir,
)
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
6. Implement: title screen → bilingual rules overlay → gameplay → win/lose state
   → restart on click/tap/Enter.
7. Follow the VISUAL RECIPE in CLAUDE.md literally: palette hex codes,
   typography, motion vocabulary, audio cues, DO-NOTs. Do not deviate.
8. Adapt patterns from the PLAYBOOK section — do not paste verbatim if they
   conflict with the recipe.
9. Playable round must complete in ~30-60 s and be clearly winnable / losable.

10. **Bilingual in-game rules screen (REQUIRED, on the title or first-open):**
    - Heading: a short title line (English + 中文).
    - Three sections, EACH with both 中文 and English copy stacked:
        · GOAL / 目標 — how to win, in one sentence
        · CONTROLS / 操作 — exact buttons / keys / taps / swipes for desktop AND mobile
        · RULES / 玩法 — scoring, penalties, special events, time limits — 2-4 bullets
    - The Chinese half MAY use Traditional Chinese (繁體) selectively for
      headings or single-word labels. Body copy can be Simplified.
    - English half must be clear and complete even to a reader who skips Chinese.
    - Dismiss the rules with the same tap/click/Enter that starts play.

11. **Replayability juice (REQUIRED):**
    - Difficulty ramps within a single round — at least one visible
      escalation moment (speed-up, denser hazards, new pattern, etc).
    - On every meaningful event (score, miss, win, fail), trigger a quick
      visual + audio cue (screen flash / shake / particle / chord).
    - The fail screen invites the user back: include both a 中文 prompt
      ("再來一次 / 再来一次") AND an English one ("Tap to replay").

Use Write tool. Do not use Bash, Read, or Edit.
"""


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

    On any exception the SDK generator is explicitly closed so its
    ``finally`` chain runs and the ``claude`` subprocess receives SIGTERM.
    Calling ``iterator.__anext__()`` directly bypasses the cleanup that
    ``async for`` would have triggered on exception.
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
            info = message.rate_limit_info  # type: ignore[attr-defined]
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


async def generate_via_sdk(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    *,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    from claude_agent_sdk import ClaudeAgentOptions, query

    game_id, game_dir, _claude_md = new_game_dir(
        concept, style_triplet_summary, visual_recipe_name
    )
    if on_start is not None:
        on_start(str(game_dir))

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Write"],
        permission_mode="bypassPermissions",
        cwd=str(game_dir),
        max_turns=8,
    )

    logger.info(f"generate-sdk: game_id={game_id} cwd={game_dir} recipe={visual_recipe_name}")
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
    logger.info(f"generate-sdk: game_id={game_id} writes={write_calls}")

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
