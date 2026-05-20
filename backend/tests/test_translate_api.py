"""Translate engine API-path tests — verify httpx call shape + error handling."""

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
        # Production code now passes its own retrying transport. Strip it and
        # substitute the MockTransport so the handler controls the response.
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=transport, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


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
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"candidates":[]}'}],
                "stop_reason": "end_turn",
            },
        )

    _patch_client_with(monkeypatch, handler)
    out = await engine._call_claude("you are X", "do the thing")

    assert out == '{"candidates":[]}'
    assert captured["url"] == "https://test.example.com/v1/messages"
    assert captured["api_key"] == "sk-test"
    assert captured["payload"]["model"] == "claude-sonnet-4-6"
    assert captured["payload"]["system"] == "you are X"
    assert captured["payload"]["messages"][0]["content"] == "do the thing"


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
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream blew up")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="500"):
        await engine._call_claude("s", "u")


async def test_call_claude_drops_non_text_content_blocks(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Anthropic responses can contain tool_use blocks; we only want text."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "tool_use", "id": "abc", "name": "X", "input": {}},
                    {"type": "text", "text": "the only text"},
                ]
            },
        )

    _patch_client_with(monkeypatch, handler)
    assert await engine._call_claude("s", "u") == "the only text"


async def test_call_claude_empty_content_array_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression: proxy returns 200 with no text blocks must surface a clear
    RuntimeError instead of letting json.JSONDecodeError fire downstream."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": [], "stop_reason": "max_tokens"},
        )

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="no text content"):
        await engine._call_claude("s", "u")


async def test_call_claude_concatenates_multiple_text_blocks(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Sonnet sometimes splits long outputs across multiple text blocks."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": '{"candi'},
                    {"type": "text", "text": 'dates":[]}'},
                ]
            },
        )

    _patch_client_with(monkeypatch, handler)
    assert await engine._call_claude("s", "u") == '{"candidates":[]}'


async def test_call_claude_timeout_surfaces_informative_runtime_error(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression: httpx.ReadTimeout has str(exc) == '' which produced the
    bare 'translation failed:' user-facing message in prod (PR #29). The
    wrapper must convert it into a RuntimeError carrying timeout + type."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="timed out after .*s.*ReadTimeout"):
        await engine._call_claude("s", "u")


async def test_call_claude_connect_error_eventually_surfaces_after_retries(
    monkeypatch: pytest.MonkeyPatch, patch_settings: None
) -> None:
    """Regression: aipaibox proxy occasionally RST-resets the TCP/TLS handshake.
    After all retries (transport-level + wrapper-level) are exhausted, the
    final RuntimeError must mention 'upstream busy' + how many attempts +
    the ConnectError detail so it's actionable."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset by peer")

    _patch_client_with(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=r"upstream busy after \d+ attempts.*ConnectError"):
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
            return httpx.Response(503, text='{"error":{"message":"No available channel for model claude-sonnet-4-6"}}')
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"candidates":[]}'}]})

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

        def handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(status, text="upstream issue")
            return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

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
