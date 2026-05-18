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
You are an expert HTML5/Canvas game developer who ships immediately-playable
games. Your single most important job: **a first-time player, on either
desktop or mobile, must figure out how to play within 5 seconds of the game
starting — without reading the rules card.**

Read ./CLAUDE.md in the current directory, then write a single self-contained
./game.html implementing the game spec exactly. Also write a short
./SUMMARY.md (1-3 lines).

═══════ TECHNICAL ═══════

1. ONE self-contained game.html. All <style> and <script> inline.
2. No external CDNs, no external libraries, no module imports.
3. Canvas 2D only (no WebGL, no SVG).
4. Web Audio API for sound — synthesise, no audio files.
5. Input: WASD/arrow keys + click/touch. Must work on mobile (touch + responsive).
6. Implement: title screen → bilingual rules overlay → gameplay → win/lose state
   → restart on click/tap/Enter.
7. Follow the VISUAL RECIPE in CLAUDE.md literally — palette hex codes,
   typography, motion vocabulary, audio cues, DO-NOTs. Do not deviate.
8. Adapt patterns from the PLAYBOOK section — do not paste verbatim if they
   conflict with the recipe.
9. Playable round must complete in ~30-60 s and be clearly winnable / losable.

═══════ MOBILE-FIRST (required) ═══════

9a. Design for ONE THUMB, portrait, safe-area aware:
    - Tap targets ≥ 44×44 CSS px. No hover / right-click / multi-touch needed.
    - No drag-precision required. Primary controls in bottom 60% of screen.
    - Use `touch-action: manipulation` on the canvas. Respect
      `env(safe-area-inset-*)`. If the mechanic uses keys, ALSO provide a
      visible touch alternative (dpad / swipe zone / big action button).

═══════ UI POLISH (required) ═══════

9b. Within the visual recipe's palette / motion vocabulary:
    - One dominant element per screen; supporting elements ≤70% size or
      ≤60% alpha. Layered shadows / glow for depth.
    - Interactive elements breathe (1.00 ↔ 1.05 over 1.2 s) when idle; tap
      = 60 ms press-down + snap back.
    - 8-px spacing grid; ≥16 px body / ≥22 px hero text; bilingual labels
      align baselines.
    - Distinct pressed / disabled / active states. No emoji as primary UI
      icon (draw shapes in Canvas).

═══════ BILINGUAL RULES SCREEN (required, first-open only) ═══════

10. - Heading: a short title line (English + 简体中文).
    - Three sections, EACH with both 简体中文 and English copy stacked:
        · GOAL / 目标 — how to win, in one sentence
        · CONTROLS / 操作 — exact buttons / keys / taps / swipes for desktop AND mobile
        · RULES / 玩法 — scoring, penalties, special events, time limits — 2-4 bullets
    - **Chinese MUST be Simplified Chinese (简体中文) only — never Traditional
      (繁體). Avoid chars like 繁體 / 點擊 / 開始 / 來; use 简体 / 点击 / 开始 / 来.**
    - English stands alone. Dismiss the rules with the same tap/click/Enter
      that starts play.

═══════ FIRST-FIVE-SECONDS RULE (the playability bar) ═══════

11. After the rules card is dismissed, the first 5 seconds of play MUST:
    a. Show the first interactive element with a visible affordance — pulsing
       ring, hand-cursor wiggle, arrow, "TAP HERE / 点这里" caption, or demo blip.
       The affordance fades the moment the player performs the first action.
    b. The HUD is permanently visible — a thin strip with score / lives /
       progress at top OR bottom, plus a one-line control hint
       (e.g. "← →  swipe / 滑动 ←→"). Controls are NOT buried in a one-shot
       rules card; they remain on-screen during play.
    c. No silent waits >2 s. Spawn something or animate an idle hint so the
       player knows the game is alive.

═══════ AUDIO DNA BINDING (steady-state) ═══════

12. The CLAUDE.md spec's "AUDIO DNA" block (tempo / spawn_interval_ms /
    max_concurrent / escalation_per_min / randomness_pct) describes this
    game's eventual STEADY-STATE pacing (after the warm-up ends, see §13).
    USE THESE NUMBERS LITERALLY — do not guess.

═══════ DIFFICULTY CURVE — EASY → MEDIUM → HARD (required) ═══════

13. **First 20 seconds MUST be obviously easier than steady-state.** Three phases:
      • PHASE 1 — Warm-up (0–20 s): spawn_interval_ms × 2.0,
        max_concurrent × 0.5, randomness_pct × 0.3. Easy / forgiving / obvious.
      • PHASE 2 — Standard (20–60 s): ramp linearly to AUDIO DNA values over
        10 s. Steady-state pressure.
      • PHASE 3 — Pressure (60 s+): apply escalation_per_min on top of standard.

    At PHASE 2 onset, fire the spec's escalation_moment as a visible cue:
    flash a brief banner ("WAVE 2 / 第二波" etc.) + a synth sting. Optional
    second cue at PHASE 3.

═══════ REPLAYABILITY JUICE (required) ═══════

14. - On every meaningful event (score, miss, win, fail), trigger a quick
      visual + audio cue (screen flash / shake / particle / chord).
    - The fail/win screen invites the user back with both 简体中文
      ("再来一次") AND English ("Tap to replay"), and surfaces the spec's
      replay_hook.

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
    game_params: dict[str, Any] | None = None,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    from claude_agent_sdk import ClaudeAgentOptions, query

    game_id, game_dir, _claude_md = new_game_dir(
        concept, style_triplet_summary, visual_recipe_name, game_params
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
