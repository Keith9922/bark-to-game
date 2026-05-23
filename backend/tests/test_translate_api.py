"""Translate engine API-path tests — verify streaming call shape + retry policy.

The engine streams the response as SSE so we have to construct event-stream
bodies for the MockTransport. ``sse_body`` is a tiny helper that wraps text
deltas + a final ``[DONE]`` marker the way Anthropic does.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from bark_to_game import settings
from bark_to_game.generate._common import RateLimitedError
from bark_to_game.translate import engine

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_client_with(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    transport = httpx.MockTransport(handler)

    def factory(**kw: Any) -> httpx.AsyncClient:
        # Production code may pass its own transport (none in current engine,
        # but keep the strip-and-replace pattern for forward compatibility).
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=transport, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def sse_body(*text_deltas: str, with_done: bool = True) -> bytes:
    """Build an SSE response body emitting the given text deltas in order.

    Each delta is a ``content_block_delta`` event with ``text_delta`` payload —
    the only event type the engine collects into the final string.
    """
    lines: list[str] = []
    for text in text_deltas:
        event = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text},
        }
        lines.append(f"data: {json.dumps(event)}\n")
    if with_done:
        lines.append("data: [DONE]\n")
    # SSE frames are double-newline-separated.
    return ("\n".join(lines) + "\n").encode()


def sse_response(*text_deltas: str) -> httpx.Response:
    return httpx.Response(
        200,
        content=sse_body(*text_deltas),
        headers={"content-type": "text/event-stream"},
    )


@pytest.fixture
def patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "API_KEY", "sk-test")
    monkeypatch.setattr(settings, "API_BASE_URL", "https://test.example.com")
    monkeypatch.setattr(settings, "API_TRANSLATE_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(settings, "API_TRANSLATE_MAX_OUTPUT_TOKENS", 4096)
    # Zero backoffs so retry tests don't sleep for seconds.
    monkeypatch.setattr(engine, "_RETRY_BACKOFFS_S", (0.0, 0.0))


async def test_call_claude_sends_correct_payload_and_returns_text(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-api-key")
        captured["payload"] = json.loads(request.content)
        return sse_response('{"candidates":[]}')

    _patch_client_with(monkeypatch, handler)
    out = await engine._call_claude("you are X", "do the thing")

    assert out == '{"candidates":[]}'
    assert captured["url"] == "https://test.example.com/v1/messages"
    assert captured["api_key"] == "sk-test"
    assert captured["payload"]["model"] == "claude-sonnet-4-6"
    assert captured["payload"]["system"] == "you are X"
    assert captured["payload"]["messages"][0]["content"] == "do the thing"
    assert captured["payload"]["stream"] is True, "streaming required for idle bound"


async def test_call_claude_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "API_KEY", None)
    with pytest.raises(RuntimeError, match="BARK_API_KEY"):
        await engine._call_claude("sys", "user")


async def test_call_claude_429_raises_rate_limited(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text='{"error":"rate"}')

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RateLimitedError):
        await engine._call_claude("s", "u")


async def test_call_claude_500_raises_runtime(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """500 isn't in the retryable set — fail fast."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream blew up")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="500"):
        await engine._call_claude("s", "u")


async def test_call_claude_ignores_non_text_deltas(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Streaming responses interleave non-text deltas (tool_use, signature_delta,
    content_block_start, etc); we only collect ``text_delta``."""

    def handler(_request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"type":"message_start","message":{}}\n\n'
            b'data: {"type":"content_block_start","index":0}\n\n'
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"..."}}\n\n'
            b'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"the only text"}}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    _patch_client_with(monkeypatch, handler)
    assert await engine._call_claude("s", "u") == "the only text"


async def test_call_claude_empty_stream_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression: stream completes with zero text deltas → surface a clear
    RuntimeError instead of letting downstream json.loads('') fire."""

    def handler(_request: httpx.Request) -> httpx.Response:
        body = b"data: [DONE]\n\n"
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="empty stream"):
        await engine._call_claude("s", "u")


async def test_call_claude_concatenates_text_deltas(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Streaming output arrives in chunks; we concatenate them in order."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return sse_response('{"candi', 'dates":[]}')

    _patch_client_with(monkeypatch, handler)
    assert await engine._call_claude("s", "u") == '{"candidates":[]}'


async def test_call_claude_connect_error_eventually_surfaces_after_retries(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression: aipaibox proxy occasionally RST-resets the TCP/TLS handshake.
    After all retries are exhausted, the final RuntimeError must mention
    'upstream busy' + how many attempts + the ConnectError detail."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset by peer")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(
        RuntimeError, match=r"upstream busy after \d+ attempts.*ConnectError"
    ):
        await engine._call_claude("s", "u")


async def test_call_claude_retries_on_503_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression for the aipaibox 'No available channel' burst seen in prod
    May-20: HTTP 503 from the proxy means a cheap-tier channel is saturated
    for a few seconds. We must retry, not fail the user."""

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(
                503,
                text='{"error":{"message":"No available channel for model claude-sonnet-4-6"}}',
            )
        return sse_response('{"candidates":[]}')

    _patch_client_with(monkeypatch, handler)
    out = await engine._call_claude("s", "u")
    assert out == '{"candidates":[]}'
    assert call_count["n"] == 3, "should have retried twice before succeeding"


async def test_call_claude_503_exhausts_retry_budget_then_clean_error(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """If 503 persists past the retry budget, surface 'upstream busy', not
    the raw nested JSON from the upstream error body."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text='{"error":{"message":"No available channel"}}')

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=r"upstream busy after \d+ attempts.*503"):
        await engine._call_claude("s", "u")


async def test_call_claude_502_and_504_also_retried(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """502 (bad gateway) and 504 (upstream timeout) are transient too."""
    for status in (502, 504):
        call_count = {"n": 0}

        def handler(_request: httpx.Request, _status: int = status) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(_status, text="upstream issue")
            return sse_response("ok")

        _patch_client_with(monkeypatch, handler)
        out = await engine._call_claude("s", "u")
        assert out == "ok", f"status {status} didn't recover after retry"


async def test_call_claude_4xx_is_NOT_retried(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """A 400 (our payload is wrong) should fail fast, no retry — retrying
    won't fix a bad payload and just delays the error."""

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(400, text="bad request")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        await engine._call_claude("s", "u")
    assert call_count["n"] == 1, "4xx must NOT be retried"


async def test_call_claude_retries_on_readtimeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression for the May-23 prod 502 ReadTimeout: the upstream Claude
    model occasionally takes >60s of silence before delivering the first byte.
    Per-idle ReadTimeout must feed the same transient-retry budget as 5xx so
    a busy channel doesn't 502 the user on the first attempt."""

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise httpx.ReadTimeout("read timed out (no bytes for 60s)")
        return sse_response('{"candidates":[]}')

    _patch_client_with(monkeypatch, handler)
    out = await engine._call_claude("s", "u")
    assert out == '{"candidates":[]}'
    assert call_count["n"] == 2, "should have retried after the first ReadTimeout"


async def test_call_claude_readtimeout_exhausts_retry_budget_then_clean_error(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """If ReadTimeout persists past the retry budget, the final RuntimeError
    must call out the timeout type so we can diagnose without grep-spelunking
    through stacktraces."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(
        RuntimeError, match=r"upstream busy after \d+ attempts.*ReadTimeout"
    ):
        await engine._call_claude("s", "u")


async def test_call_claude_overloaded_stream_error_is_retried(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Streamed responses can deliver an in-band error event before any text.
    'overloaded_error' is the SSE equivalent of HTTP 503 — same retry logic."""

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            body = (
                b'data: {"type":"error","error":{"type":"overloaded_error","message":"slow down"}}\n\n'
                b"data: [DONE]\n\n"
            )
            return httpx.Response(
                200, content=body, headers={"content-type": "text/event-stream"}
            )
        return sse_response("recovered")

    _patch_client_with(monkeypatch, handler)
    out = await engine._call_claude("s", "u")
    assert out == "recovered"
    assert call_count["n"] == 2
