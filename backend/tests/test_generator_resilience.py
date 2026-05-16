"""Resilience tests for the generator: rate-limit detection + watchdog."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator
from typing import Any

import pytest

from bark_to_game.generate import generator
from bark_to_game.schemas.game import JobEvent

# ---- stub claude_agent_sdk module ----------------------------------------
#
# generator._drain imports RateLimitEvent at call time. We monkeypatch the
# module so the test doesn't depend on the real SDK and so we can fabricate
# rate-limit messages with arbitrary payloads.


class _FakeRateLimitInfo:
    def __init__(self, status: str, resets_at: int | None = 1700000000) -> None:
        self.status = status
        self.resets_at = resets_at
        self.rate_limit_type = "five_hour"
        self.utilization = 1.0


class _FakeRateLimitEvent:
    def __init__(self, status: str, resets_at: int | None = 1700000000) -> None:
        self.rate_limit_info = _FakeRateLimitInfo(status, resets_at)


@pytest.fixture(autouse=True)
def _stub_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("claude_agent_sdk")
    fake.RateLimitEvent = _FakeRateLimitEvent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)


def _stream(items: list[Any]) -> AsyncIterator[Any]:
    async def _gen() -> AsyncIterator[Any]:
        for x in items:
            yield x

    return _gen()


# ---- tests ---------------------------------------------------------------


async def test_drain_raises_on_rate_limit_rejected() -> None:
    events: list[JobEvent] = []
    with pytest.raises(generator.RateLimitedError) as exc_info:
        await generator._drain(
            _stream([_FakeRateLimitEvent(status="rejected", resets_at=1700001234)]),
            publish=events.append,
        )
    assert exc_info.value.resets_at == 1700001234
    # A rate_limit event was published before raising.
    assert len(events) == 1
    assert events[0].type == "rate_limit"
    assert events[0].data["status"] == "rejected"


async def test_drain_ignores_allowed_warning_keeps_going() -> None:
    events: list[JobEvent] = []
    write_calls = await generator._drain(
        _stream([_FakeRateLimitEvent(status="allowed_warning")]),
        publish=events.append,
    )
    assert write_calls == 0
    assert [e.type for e in events] == ["rate_limit"]


async def test_drain_watchdog_fires_on_idle_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generator, "IDLE_TIMEOUT_S", 0.05)

    async def _never() -> AsyncIterator[Any]:
        await asyncio.sleep(10)
        yield None  # never reached

    with pytest.raises(generator.GenerationStalledError):
        await generator._drain(_never(), publish=None)


# The drain function publishes a "message" event for any class named
# AssistantMessage / UserMessage / SystemMessage — matching the SDK's own
# class names. We mirror that naming here.
class AssistantMessage:
    content: list[Any] = []


async def test_drain_completes_normally_on_exhausted_stream() -> None:
    events: list[JobEvent] = []
    write_calls = await generator._drain(
        _stream([AssistantMessage()]),
        publish=events.append,
    )
    assert write_calls == 0
    assert [e.type for e in events] == ["message"]


async def test_drain_counts_write_tool_calls_and_publishes() -> None:
    events: list[JobEvent] = []

    class _Block:
        name = "Write"
        input = {"file_path": "/tmp/game.html"}

    class AssistantMessage:  # shadows the outer one — intentional
        content = [_Block()]

    write_calls = await generator._drain(
        _stream([AssistantMessage()]),
        publish=events.append,
    )
    assert write_calls == 1
    types_seen = [e.type for e in events]
    assert "write" in types_seen
    assert "message" in types_seen
    write_event = next(e for e in events if e.type == "write")
    assert write_event.data["file_path"] == "/tmp/game.html"
