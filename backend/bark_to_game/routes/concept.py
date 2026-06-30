"""Token sequence → game concept translation endpoint.

The route returns an **NDJSON stream**, not a single JSON document:
heartbeat lines (a single space + ``\\n``) are emitted every few seconds
while the upstream model is generating, and the final line is the real
``TranslateResponse`` payload (or an ``{"error": ...}`` object).

Why streaming: a single translate call to claude-sonnet-4-6 through the
aipaibox proxy routinely takes 60-270 s on busy channels. A plain JSON
response would block the HTTP connection for that long, and Cloudflare's
quick-tunnel edge enforces a 100 s response-start timeout (HTTP 524). By
streaming heartbeats from the moment the request lands, Cloudflare sees
continuous bytes and never trips the 524. The total request can now run
for as long as ``translate()`` needs.

The frontend parses the stream line-by-line, ignoring heartbeats, and
treats the last non-empty line as the result.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from bark_to_game.schemas.concept import (
    Concept,
    GameParams,
    StyleCardRef,
    StyleTriplet,
    TranslateRequest,
    TranslateResponse,
)
from bark_to_game.translate.engine import TranslationResult, translate

router = APIRouter(prefix="/api/concept", tags=["concept"])

# How often to emit a heartbeat newline while waiting for translate to finish.
# Must be well under Cloudflare's 100 s response-start timeout. Five seconds
# leaves margin for the very first delta to also be a heartbeat without
# anything close to the edge.
_HEARTBEAT_INTERVAL_S = 5.0

# Single-byte payload kept to a minimum so the running total stays cheap even
# on a 5-minute translate. A space avoids "empty line" semantics so any naive
# parser that splits on '\n' still treats heartbeats as ignorable noise.
_HEARTBEAT_LINE = b" \n"


def _user_friendly_translate_error(exc: BaseException) -> str:
    """Translate engine exception → message the frontend can show verbatim.

    The engine has its own retry loop for transient failures (5xx, ReadTimeout,
    ConnectError, overloaded_error). Anything that bubbles up here has already
    survived 3 attempts, so a friendly "上游响应慢，请稍后重试" beats the raw
    "upstream busy after N attempts (last: ...)" stack chatter.

    We classify by the engine's wrapper message pattern, falling back to the
    raw exception text so unfamiliar failure modes are still debuggable.
    """
    detail = str(exc) or type(exc).__name__
    if "upstream busy" in detail or "ReadTimeout" in detail or "ConnectError" in detail:
        return (
            "上游响应慢，已自动重试仍未成功，请稍后再试一次。 "
            "(Upstream slow after retries — please try again in a few seconds.)"
        )
    if "rate-limited" in detail or "HTTP 429" in detail:
        return (
            "今日 API 额度已用尽，请稍后再试。"
            "(API quota exhausted — try later.)"
        )
    # Unknown failure — keep the developer-readable detail so we can debug
    # without leaving the user with an opaque error.
    body = f"{type(exc).__name__}: {exc!s}" if str(exc) else type(exc).__name__
    return f"translation failed: {body}"


def _translate_response_dict(result: TranslationResult) -> dict[str, object]:
    """Build the wire-shape dict directly. Avoids constructing a Pydantic
    model only to immediately serialise it — same outcome, half the work."""
    triplet = result["style_triplet"]
    return TranslateResponse(
        chosen=Concept(**result["chosen"]),
        chosen_probability=result["chosen_probability"],
        chosen_score=result["chosen_score"],
        candidate_count=len(result["candidates"]),
        style_triplet=StyleTriplet(
            art=StyleCardRef(
                name=triplet["art"]["name"], description=triplet["art"]["description"]
            ),
            mechanic=StyleCardRef(
                name=triplet["mechanic"]["name"],
                description=triplet["mechanic"]["description"],
            ),
            mood=StyleCardRef(
                name=triplet["mood"]["name"], description=triplet["mood"]["description"]
            ),
        ),
        visual_recipe=result["visual_recipe"],
        game_params=GameParams(**result["game_params"]),
        avoided_summaries=result["avoided_summaries"],
    ).model_dump(mode="json")


async def _translate_ndjson_stream(req: TranslateRequest) -> AsyncIterator[bytes]:
    """Heartbeat-driven NDJSON stream for /translate.

    Heartbeats keep Cloudflare's response timer alive; the real translate
    runs as a background task so we can interleave them cleanly. We use
    ``asyncio.shield`` so a heartbeat's ``wait_for`` cancellation never tears
    down the translate task itself, and the ``finally`` clause cancels any
    still-running task on early generator close — covers both
    ``CancelledError`` (server cancel) and ``GeneratorExit`` (consumer
    ``aclose()``) without two near-identical except blocks.
    """
    task: asyncio.Task[TranslationResult] = asyncio.create_task(
        translate(
            tokens=[t.model_dump() for t in req.tokens],
            summary=req.summary.model_dump(),
            audio_hash=req.audio_hash,
            session_id=req.session_id,
        )
    )

    try:
        # First heartbeat immediately so Cloudflare sees TTFB inside its
        # window even if translate's very first network call takes the full
        # connect timeout to allocate a channel.
        yield _HEARTBEAT_LINE

        while not task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(task), timeout=_HEARTBEAT_INTERVAL_S
                )
            except TimeoutError:
                yield _HEARTBEAT_LINE
            except Exception:
                # The task itself raised. ``wait_for`` re-raises the inner
                # exception; break and let the done-branch render the error
                # frame using ``task.exception()`` so the error wrapping
                # stays in one place.
                break

        # Task settled. The exception path mirrors the old non-streaming
        # route's 502 wrapping so the frontend's error UX is unchanged.
        if (exc := task.exception()) is not None:
            if isinstance(exc, ValueError):
                # 400-class — bad payload. Surface via NDJSON with a status
                # hint so the frontend can render the same way it does today.
                yield (
                    json.dumps({"error": str(exc), "status": 400}, ensure_ascii=False)
                    + "\n"
                ).encode()
                return
            detail = _user_friendly_translate_error(exc)
            logger.warning(f"translate route: 502 — {exc!r}")
            yield (
                json.dumps({"error": detail, "status": 502}, ensure_ascii=False)
                + "\n"
            ).encode()
            return

        payload = _translate_response_dict(task.result())
        yield (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    finally:
        # If the consumer aborts us (StreamingResponse cancellation, or the
        # client closing the connection so FastAPI cancels the request task)
        # the underlying translate is still running. Cancel it so we don't
        # keep burning aipaibox tokens for a response no one will read.
        if not task.done():
            task.cancel()


@router.post("/translate")
async def translate_tokens(req: TranslateRequest) -> StreamingResponse:
    """NDJSON-streaming translate. See module docstring for protocol.

    Returns 200 + ``application/x-ndjson`` regardless of translate outcome —
    callers must read the final line of the stream to learn success vs
    failure. This is the price of being Cloudflare-safe: an HTTP-level
    error code would require the headers to be sent before we know the
    outcome, which would defeat the purpose of the heartbeat keep-alive.
    """
    return StreamingResponse(
        _translate_ndjson_stream(req),
        media_type="application/x-ndjson",
    )


# Kept for the test suite — exercise the validation + happy-path translation
# logic without going through the streaming wrapper. Production traffic uses
# the route above. Marked private so it doesn't end up in the OpenAPI surface.
async def _translate_sync(req: TranslateRequest) -> dict[str, object]:
    try:
        result = await translate(
            tokens=[t.model_dump() for t in req.tokens],
            summary=req.summary.model_dump(),
            audio_hash=req.audio_hash,
            session_id=req.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            _user_friendly_translate_error(exc),
        ) from exc
    return _translate_response_dict(result)
