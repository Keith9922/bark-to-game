"""Generation via direct Anthropic Messages API (proxied through aipaibox).

Why this exists: the SDK backend shares the Claude Max plan quota with the
user's interactive Claude Code window. When that window is active, SDK calls
get silently rate-limited (no ``RateLimitEvent`` emitted) and the watchdog has
to kill them after 120 s. Switching to a paid API key with its own quota
removes the contention.

How it works: single streaming ``POST /v1/messages`` to the configured proxy,
asking Claude to output the entire ``game.html`` inside one ```html``` code
block followed by a ```markdown``` summary block. We stream-collect the
response, parse the blocks, and write the files ourselves.

This is much simpler than the SDK's tool-use loop because we only ever need
one file written; the agent loop was overkill.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from bark_to_game import settings
from bark_to_game.generate._common import (
    GenerationResult,
    GenerationStalledError,
    RateLimitedError,
    new_game_dir,
)
from bark_to_game.schemas.game import JobEvent

# How long the entire request can take. Game generations on Opus take 60-180 s
# in the wild; we set a generous ceiling so a slow run doesn't false-positive.
REQUEST_TIMEOUT_S = 300.0

# Per-event idle bound: if we receive zero SSE bytes for this long, abort.
# Anthropic streaming typically pings every ~15 s during long generations.
IDLE_TIMEOUT_S = 90.0

# Inject as the system prompt — keeps user-prompt focused on the spec.
SYSTEM_PROMPT = """\
You are an expert HTML5/Canvas game developer who ships **immediately
playable** games. Your single most important job is: **a first-time player,
on either desktop or mobile, must figure out how to play within 5 seconds of
the game starting — without reading the rules card.**

When the user gives you a game spec, output a single playable game as a
self-contained HTML file. Non-negotiable constraints:

═══════ TECHNICAL ═══════

1. ONE self-contained game.html. All <style> and <script> inline.
2. No external CDNs, no external libraries, no module imports.
3. Canvas 2D only (no WebGL, no SVG).
4. Web Audio API for sound — synthesise, no audio files.
5. Input: WASD/arrow keys + click/touch. Must work on mobile (touch + responsive).
6. Implement: title screen → bilingual rules overlay → gameplay → win/lose state
   → restart on click/tap/Enter.
7. Follow the VISUAL RECIPE in the spec literally: palette hex codes,
   typography, motion vocabulary, audio cues, DO-NOTs. Do not deviate.
8. Adapt PLAYBOOK patterns — do not paste verbatim if they clash with the recipe.
9. Playable round must complete in ~30-60 s and be clearly winnable / losable.

═══════ MOBILE-FIRST (required — most users open on phone) ═══════

9a. Design for ONE THUMB, portrait orientation, in safe-area insets:
    - Every tap target ≥ 44×44 CSS px. Pad small hit zones generously.
    - NO reliance on hover, right-click, or multi-touch gestures.
    - NO drag-precision requirements (no "draw an exact circle"). Swipe-then-
      release is OK; pixel-precise pointer trails are not.
    - Place primary controls in the bottom 60% of screen — top is hard to reach.
    - Use `touch-action: manipulation` on the canvas to kill the 300ms tap delay.
    - Respect `env(safe-area-inset-*)` so notch / home bar don't clip controls.
    - Test mentally: can a one-handed thumb finish a full round on a 6.1" phone
      with the device gripped? If not, redesign the input scheme.
    - When the mechanic naturally uses keys (arrows / WASD), STILL provide a
      visible on-screen touch alternative (dpad, swipe zone, big action button).

═══════ UI POLISH (required — feel premium, not student-project) ═══════

9b. Apply within the visual recipe's palette / motion vocabulary:
    - **Hierarchy**: one dominant element per screen (title / hero target /
      score). Supporting elements at ≤70% size or ≤60% alpha.
    - **Depth**: layered shadows or glow for foreground, flatter background.
      Cheap and effective: `ctx.shadowBlur` + `shadowColor`, OR a 2-px offset
      same-colour underlay rectangle.
    - **Micro-motion**: every interactive element breathes (scale 1.00 ↔ 1.05
      over 1.2 s) when idle so it reads as "tappable". Tap = 60 ms scale-down
      "press" feedback, then snap back.
    - **Spacing**: respect an 8-px grid. No element touches another without
      intentional negative space (≥ 8 px).
    - **Type**: ≥ 16 px body, ≥ 22 px hero. Bilingual labels use the same
      weight; align baselines, never centre one and left-align the other.
    - **States**: pressed, disabled (40% alpha), active — all visually distinct.
      NEVER leave a button looking the same across all states.
    - **No emoji as primary UI icon** unless the recipe explicitly calls for
      it. Draw shapes with Canvas; emoji breaks the recipe's palette.

═══════ BILINGUAL RULES SCREEN (required, shown ONCE on first-open) ═══════

10. - Heading: a short title line (English + 简体中文).
    - Three sections, EACH with both 简体中文 and English copy stacked:
        · GOAL / 目标 — how to win, in one sentence
        · CONTROLS / 操作 — exact buttons / keys / taps / swipes for desktop AND mobile
        · RULES / 玩法 — scoring, penalties, special events, time limits — 2-4 bullets
    - **Chinese MUST be Simplified Chinese (简体中文) only — never Traditional
      (繁體). Avoid characters like 繁體 / 點擊 / 開始 / 來 / 進 / 點 etc.**
      Correct examples: 简体 / 点击 / 开始 / 来 / 进 / 点.
    - English half is the primary fallback: must be clear and complete
      even to a reader who skips the Chinese.
    - Dismiss the rules with the same tap/click/Enter that starts play.

═══════ FIRST-FIVE-SECONDS RULE (the playability bar) ═══════

11. After the rules card is dismissed, the first 5 seconds of play MUST:
    a. **Show the first interactive element with a visible affordance** —
       a pulsing ring, a hand-cursor wiggle, an arrow, a "TAP HERE / 点这里"
       caption, or a slow demo blip. The affordance fades out the moment the
       player successfully performs the first action.
    b. **The HUD must be permanently visible** — a thin strip with score /
       lives / progress at the top OR bottom edge, plus a one-line
       control-hint that updates contextually (e.g. "← →  swipe / 滑动 ←→").
       Do NOT bury controls in a one-shot rules card; they must be a
       constant reminder during play.
    c. **No silent waits >2s.** If nothing happens, spawn something or
       animate an idle hint so the player knows the game is alive.

═══════ AUDIO DNA BINDING (required) ═══════

12. The spec includes a block called "AUDIO DNA" with concrete integers
    (tempo / spawn_interval_ms / max_concurrent / escalation_per_min /
     randomness_pct). USE THESE NUMBERS LITERALLY — do not guess your own
    timing. They are the bark-derived pacing for THIS specific game's
    eventual STEADY-STATE pacing (not the opening 20 s, see §13).
    - spawn_interval_ms → eventual base setInterval / time-between-spawns
    - max_concurrent    → eventual cap on entity array length
    - escalation_per_min → multiply spawn rate (or whatever pacing knob fits)
      by this factor every 60 s of play (after the warm-up ends)
    - randomness_pct    → ±% jitter on spawn timings and positions

═══════ DIFFICULTY CURVE — EASY → MEDIUM → HARD (required) ═══════

13. **The FIRST ROUND must be obviously winnable by a first-time player who
    has never seen the game before.** "Round 1 cleared" is the single most
    important moment in the whole session — if the player can't reach it
    inside ~30 s of casual play, the design has failed.

    a. **First-round difficulty floor (HARD RULES, override the concept text
       if the two clash):**
       - At most **HALF** the steady-state quantity (sprites / blocks /
         enemies / cards / cells). If the concept text says "three ghosts",
         spawn ONE in round 1, scale up later. If it says "twelve to win",
         require THREE for round 1, scale up.
       - No fail condition can trigger in the first 20 s — the warm-up is a
         no-fail tutorial. Track strikes / lives / breaches, but mute the
         lose() call until 20 s have elapsed. If the player would have lost
         during warm-up, just reset that strike and let them play on.
       - The win condition for the FIRST ROUND must be reachable in ≤ 30 s
         of normal play. Scale quotas accordingly — better to start with a
         "trivial" round and ramp than to gate everyone behind a hard wall.
       - Movement / spawn speeds: spawn_interval_ms × 2.0, max_concurrent
         × 0.5, randomness_pct × 0.3, and any "auto enemy" wander/aggression
         × 0.5 too. The opening must FEEL slow.

    b. **Full curve** (round-based games map "round N" to time bucket):
       • PHASE 1 — Warm-up (round 1, ~0–20 s): rules in (a). No-fail.
       • PHASE 2 — Standard (rounds 2–3, ~20–60 s): ramp linearly to AUDIO
         DNA steady-state pacing over 10 s. Failure now possible.
       • PHASE 3 — Pressure (round 4+, 60 s+): apply escalation_per_min on
         top of standard.

    c. **WIN must be reachable in 60–90 s of decent play.** If your concept
       wants "clear N waves to win", N should be 2–4, NOT 5+. If it's score-
       attack, the win threshold should fall in that time. A win that takes
       3+ minutes is worse than no win because nobody sees it.

    When PHASE 2 begins, fire the spec's **escalation_moment** as the visible
    "now it gets real" cue — brief banner ("WAVE 2 / 第二波", "+SPEED" etc.)
    plus a synth sting. Optional second cue at PHASE 3.

═══════ REPLAYABILITY JUICE (required) ═══════

14. - On every meaningful event (score, miss, win, fail), trigger a quick
      visual + audio cue (screen flash / shake / particle / chord).
    - The fail/win screen invites the user back: include both a 简体中文
      prompt ("再来一次") AND an English one ("Tap to replay") so the
      retry CTA is unambiguous. State the **replay_hook** from the spec
      (e.g. "Best score: 12 — beat it next time").

═══════ CODE SELF-CHECK (must pass before you emit the html block) ═══════

15. **Don't ship undefined behaviour.** Before closing the ```html``` block,
    mentally walk through these three checks — every shipped bug from this
    template has been one of them:

    a. **State init at declaration.** Every `let`/`const`/`var` you reference
       inside the game loop (player, items, enemies, score, target, etc.)
       MUST be initialised to a concrete value at declaration — NOT declared
       bare and "set later in init()". Use
       `let player = { x: W/2, w: 110, h: 18, lives: 3 }`,
       not `let player;` followed by `function init(){ player = {...} }`.
       Reason: a first-frame paint or input event can fire before init()
       runs and crash the game with TypeError on undefined access. Arrays:
       `let items = []`, not `let items;`.

    b. **Catch / sort / match mechanics — non-target items are FREE.**
       If your core_loop is "catch the target shape" or "sort by colour"
       or "match the prompt", then ONLY missing the actual TARGET costs a
       life. Letting a non-target fall off-screen is correct play (the
       player wisely didn't catch it). Never call `loseLife()` on a missed
       non-target — that punishes correct play and is a real-user-reported
       bug. The rules card MUST state this rule explicitly in both languages.

    c. **Round-1 dry-run.** Imagine a brand-new player who skipped the rules
       card. Walk them through the first 30 s. Do they:
       1) understand what to do in 5 s (visible affordance)?
       2) make their first successful action by 10 s?
       3) clear the round-1 win quota by 30 s under §13a halved-quantity rule?
       If any answer is "no", scale the round-1 numbers down further BEFORE
       emitting the html block.

═══════ OUTPUT FORMAT — exactly two fenced blocks, nothing else ═══════

```html
<!DOCTYPE html>
...the entire game...
</html>
```

```markdown
One to three lines describing what you built and how to play.
```
"""

# Fence pattern — match only opening fences that are alone on a line (start
# anchored, optional language tag, end of line). Closing fences are matched
# the same way to dodge stray ``` inside JS template literals etc.
_FENCE_OPEN_RE = re.compile(r"^```([A-Za-z]*)\s*$", re.MULTILINE)
_FENCE_CLOSE_RE = re.compile(r"^```\s*$", re.MULTILINE)


async def generate_via_api(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    *,
    game_params: dict[str, Any] | None = None,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    if not settings.API_KEY:
        raise RuntimeError(
            "BARK_API_KEY is not set. Either set it in backend/.env or switch "
            "BARK_GENERATOR_MODE=sdk."
        )

    game_id, game_dir, claude_md = new_game_dir(
        concept, style_triplet_summary, visual_recipe_name, game_params
    )
    if on_start is not None:
        on_start(str(game_dir))

    payload = {
        "model": settings.API_MODEL,
        "max_tokens": settings.API_MAX_OUTPUT_TOKENS,
        "stream": True,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": claude_md}],
    }
    headers = {
        "x-api-key": settings.API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    logger.info(
        f"generate-api: game_id={game_id} model={settings.API_MODEL} "
        f"recipe={visual_recipe_name}"
    )

    full_text = await _stream_messages(payload, headers, publish)

    blocks = _extract_fenced_blocks(full_text)
    html_block = next(
        (b for b in blocks if b["lang"].lower() in ("html", "")), None
    )
    if html_block is None:
        raise RuntimeError(
            f"API output did not contain a ```html``` code block "
            f"(got {len(full_text)} chars, {len(blocks)} fenced blocks found)"
        )
    game_html = html_block["body"].strip()
    game_path = game_dir / "game.html"
    game_path.write_text(game_html, encoding="utf-8")
    if publish:
        publish(
            JobEvent(
                type="write",
                ts=time.time(),
                data={"file_path": str(game_path)},
            )
        )

    md_block = next(
        (
            b
            for b in blocks
            if b["start"] > html_block["start"]
            and b["lang"].lower() in ("markdown", "md", "")
        ),
        None,
    )
    summary = (
        md_block["body"].strip()[:300] if md_block is not None else "(no summary)"
    )
    (game_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")

    logger.info(
        f"generate-api: game_id={game_id} html_bytes={len(game_html)} summary_bytes={len(summary)}"
    )

    return GenerationResult(
        game_id=game_id,
        game_path=str(game_path),
        summary=summary,
        cwd=str(game_dir),
    )


async def _stream_messages(
    payload: dict[str, Any],
    headers: dict[str, str],
    publish: Callable[[JobEvent], None] | None,
) -> str:
    """Stream the Messages API response, return the concatenated assistant text.

    Forwards per-block progress to ``publish`` and surfaces rate-limit + stall
    failures through the same error types the SDK backend uses, so the route
    layer can treat both backends identically.
    """
    timeout = httpx.Timeout(REQUEST_TIMEOUT_S, connect=30.0, read=IDLE_TIMEOUT_S)
    url = f"{settings.API_BASE_URL}/v1/messages"
    full_text_parts: list[str] = []
    last_publish_len = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code == 429:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                    resets_at = _resets_at_from_headers(resp.headers)
                    raise RateLimitedError(
                        f"API rate-limited (HTTP 429): {body}", resets_at=resets_at
                    )
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                    raise RuntimeError(
                        f"API error HTTP {resp.status_code}: {body}"
                    )

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[len("data: "):].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug(f"api: malformed SSE line: {raw[:200]}")
                        continue
                    _handle_event(event, full_text_parts, publish)

                    # Periodic preview publish so the UI sees activity.
                    total_len = sum(len(p) for p in full_text_parts)
                    if (
                        publish is not None
                        and total_len - last_publish_len >= 400
                    ):
                        last_publish_len = total_len
                        snippet = "".join(full_text_parts)[-160:]
                        publish(
                            JobEvent(
                                type="message",
                                ts=time.time(),
                                data={"kind": "AssistantMessage", "preview": snippet},
                            )
                        )
        except httpx.ReadTimeout as exc:
            raise GenerationStalledError(
                f"API stream idle for {IDLE_TIMEOUT_S:.0f}s — upstream likely stuck"
            ) from exc
        except TimeoutError as exc:
            raise GenerationStalledError(
                f"API request exceeded {REQUEST_TIMEOUT_S:.0f}s total"
            ) from exc

    return "".join(full_text_parts)


def _extract_fenced_blocks(text: str) -> list[dict[str, Any]]:
    r"""Walk fence-open / fence-close pairs and return non-overlapping blocks.

    Each entry: ``{"lang": <str>, "start": <int>, "body": <str>}``.

    Pairs sequentially rather than relying on a non-greedy regex over the
    whole text, so a stray triple-backtick line inside a JS template literal
    can't truncate the captured HTML at the wrong place. We assume Claude
    follows the system prompt's "exactly two fenced blocks" instruction —
    if it ever nests blocks inside the html block, the inner closer will
    end this block early, but that's an upstream-prompt issue.
    """
    blocks: list[dict[str, Any]] = []
    cursor = 0
    while True:
        open_match = _FENCE_OPEN_RE.search(text, pos=cursor)
        if open_match is None:
            return blocks
        body_start = open_match.end() + 1  # skip the trailing newline
        close_match = _FENCE_CLOSE_RE.search(text, pos=body_start)
        if close_match is None:
            return blocks
        body = text[body_start : close_match.start()].rstrip("\n")
        blocks.append({
            "lang": open_match.group(1),
            "start": open_match.start(),
            "body": body,
        })
        cursor = close_match.end()


def _handle_event(
    event: dict[str, Any],
    text_parts: list[str],
    publish: Callable[[JobEvent], None] | None,
) -> None:
    etype = event.get("type")
    if etype == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            text_parts.append(delta.get("text", ""))
    elif etype == "message_stop":
        # Stream terminated cleanly; let the outer code finalise.
        pass
    elif etype == "error":
        err = event.get("error") or {}
        if err.get("type") == "overloaded_error":
            raise RateLimitedError(
                f"API overloaded: {err.get('message', '?')}", resets_at=None
            )
        raise RuntimeError(f"API stream error: {err}")


def _resets_at_from_headers(headers: httpx.Headers) -> int | None:
    """Pull a unix timestamp out of the ``anthropic-ratelimit-*-reset`` headers
    if the upstream included them. Returns None when absent or unparseable."""
    for key in (
        "anthropic-ratelimit-tokens-reset",
        "anthropic-ratelimit-requests-reset",
        "retry-after",
    ):
        raw = headers.get(key)
        if not raw:
            continue
        # Anthropic emits ISO-8601 (e.g. "2026-05-17T05:00:00Z"); retry-after is
        # usually delta seconds.
        try:
            if raw.endswith("Z") or "T" in raw:
                return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
            return int(time.time()) + int(raw)
        except (TypeError, ValueError):
            continue
    return None
