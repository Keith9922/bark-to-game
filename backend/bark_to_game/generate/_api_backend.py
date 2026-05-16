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
You are an expert HTML5/Canvas game developer.

When the user gives you a game spec, output a single playable game as a
self-contained HTML file. Non-negotiable constraints:

1. ONE self-contained game.html. All <style> and <script> inline.
2. No external CDNs, no external libraries, no module imports.
3. Canvas 2D only (no WebGL, no SVG).
4. Web Audio API for sound — synthesise, no audio files.
5. Input: WASD/arrow keys + click/touch. Must work on mobile (touch + responsive).
6. Implement: title screen → gameplay → win/lose state → restart on click/tap/Enter.
7. Follow the VISUAL RECIPE in the spec literally: palette hex codes,
   typography, motion vocabulary, audio cues, DO-NOTs. Do not deviate.
8. Adapt PLAYBOOK patterns — do not paste verbatim if they clash with the recipe.
9. Playable round must complete in ~30 s and be clearly winnable / losable.

Output format — exactly two fenced blocks, nothing else:

```html
<!DOCTYPE html>
...the entire game...
</html>
```

```markdown
One to three lines describing what you built and how to play.
```
"""

# Tolerant of optional language tags and CRLF / trailing whitespace.
_HTML_BLOCK_RE = re.compile(r"```(?:html|HTML)?\s*\n(.*?)\n```", re.DOTALL)
_MD_BLOCK_RE = re.compile(r"```(?:markdown|md)?\s*\n(.*?)\n```", re.DOTALL)


async def generate_via_api(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    *,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    if not settings.API_KEY:
        raise RuntimeError(
            "BARK_API_KEY is not set. Either set it in backend/.env or switch "
            "BARK_GENERATOR_MODE=sdk."
        )

    game_id, game_dir, claude_md = new_game_dir(
        concept, style_triplet_summary, visual_recipe_name
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

    html_match = _HTML_BLOCK_RE.search(full_text)
    if not html_match:
        raise RuntimeError(
            f"API output did not contain a ```html``` code block "
            f"(got {len(full_text)} chars)"
        )
    game_html = html_match.group(1).strip()
    game_path = game_dir / "game.html"
    game_path.write_text(game_html)
    if publish:
        publish(
            JobEvent(
                type="write",
                ts=time.time(),
                data={"file_path": str(game_path)},
            )
        )

    summary_match = _MD_BLOCK_RE.search(full_text, pos=html_match.end())
    summary = (
        summary_match.group(1).strip()[:300] if summary_match else "(no summary)"
    )
    (game_dir / "SUMMARY.md").write_text(summary)

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
                from datetime import datetime

                return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
            return int(time.time()) + int(raw)
        except (TypeError, ValueError):
            continue
    return None
