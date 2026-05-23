"""/api/concept/translate route — NDJSON streaming + heartbeat behaviour.

The route used to return one JSON object. It now streams ``application/x-ndjson``:
heartbeat lines (``b" \\n"``) while translate runs, then a final line with the
real payload or an ``{"error": ..., "status": ...}`` object. Tests parse the
stream by reading the response body and splitting on newlines.

This pattern fixes Cloudflare 524s on slow upstream calls (translate against
claude-sonnet-4-6 on busy aipaibox channels can take 4+ minutes).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bark_to_game.main import app
from bark_to_game.routes import concept as concept_route
from bark_to_game.translate import archive, engine

client = TestClient(app)

_TOKEN = {
    "start_ms": 100,
    "end_ms": 300,
    "type": "BARK",
    "pitch": "LOW",
    "duration": "SHORT",
    "intensity": "LOUD",
    "contour": "FLAT",
    "confidence": 0.9,
    "source": "yamnet",
}

_SUMMARY = {"rhythm": "STACCATO", "mood": "AGITATED", "entropy": 0.4}


def _fake_payload() -> str:
    return json.dumps(
        {
            "candidates": [
                {
                    "probability": 0.5,
                    "concept": {
                        "title": "Pebble Storm",
                        "tagline": "Catch what the sky throws.",
                        "player": "a roaming pebble",
                        "core_mechanic": "dodge",
                        "win_condition": "survive 60s",
                        "fail_condition": "3 hits",
                        "visual_summary": "geometric",
                        "audio_summary": "sine waves",
                    },
                },
                {
                    "probability": 0.5,
                    "concept": {
                        "title": "Other Idea",
                        "tagline": "alt",
                        "player": "p",
                        "core_mechanic": "m",
                        "win_condition": "w",
                        "fail_condition": "l",
                        "visual_summary": "v",
                        "audio_summary": "a",
                    },
                },
            ]
        }
    )


def _ndjson_lines(body: bytes) -> list[str]:
    """Split an NDJSON body into non-empty trimmed lines."""
    return [line for line in body.decode("utf-8").splitlines() if line.strip()]


def _final_json(body: bytes) -> dict[str, Any]:
    lines = _ndjson_lines(body)
    assert lines, f"empty NDJSON body: {body!r}"
    # Drop pure-whitespace heartbeats (single space). The last line with real
    # JSON is the payload (or error object).
    payload_lines = [ln for ln in lines if ln.strip() and not ln.strip().isspace()]
    assert payload_lines, f"no payload line in NDJSON: {lines!r}"
    return json.loads(payload_lines[-1])


def test_translate_route_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)

    async def fake(_s: str, _u: str) -> str:
        return _fake_payload()

    monkeypatch.setattr(engine, "_call_claude", fake)

    response = client.post(
        "/api/concept/translate",
        json={
            "tokens": [_TOKEN],
            "summary": _SUMMARY,
            "audio_hash": "deadbeefdeadbeef",
            "session_id": "route-test",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    data = _final_json(response.content)
    assert "chosen" in data
    assert data["candidate_count"] == 2
    assert data["chosen"]["title"] in {"Pebble Storm", "Other Idea"}
    assert "style_triplet" in data
    assert "visual_recipe" in data


def test_translate_route_streams_error_object_on_sdk_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The streaming route can't change headers after starting, so failures
    are surfaced as an NDJSON ``{"error": ..., "status": ...}`` final line
    instead of an HTTP 5xx. The status code stays 200."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)

    async def boom(_s: str, _u: str) -> str:
        raise RuntimeError("simulated SDK outage")

    monkeypatch.setattr(engine, "_call_claude", boom)

    response = client.post(
        "/api/concept/translate",
        json={
            "tokens": [_TOKEN],
            "summary": _SUMMARY,
            "audio_hash": "f00df00df00df00d",
        },
    )
    assert response.status_code == 200, response.text
    final = _final_json(response.content)
    assert final.get("status") == 502
    assert "error" in final


def test_translate_route_returns_friendly_msg_for_upstream_busy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """When the engine retries are exhausted and surface 'upstream busy', the
    route must rewrite that into a bilingual human-readable detail — not echo
    the raw 'RuntimeError: translate upstream busy after 3 attempts ...'
    that the frontend would otherwise dump into a red error card."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)

    async def busy(_s: str, _u: str) -> str:
        raise RuntimeError(
            "translate upstream busy after 3 attempts "
            "(last: ReadTimeout (idle bound 60s, total bound 240s)). "
            "Try again in a few seconds."
        )

    monkeypatch.setattr(engine, "_call_claude", busy)

    response = client.post(
        "/api/concept/translate",
        json={
            "tokens": [_TOKEN],
            "summary": _SUMMARY,
            "audio_hash": "f00df00df00df00d",
        },
    )
    assert response.status_code == 200
    final = _final_json(response.content)
    assert final.get("status") == 502
    assert "上游响应慢" in final["error"], (
        f"expected bilingual upstream-busy msg, got: {final['error']}"
    )
    assert "RuntimeError" not in final["error"], (
        "raw exception type leaked into user-facing msg"
    )


async def test_translate_ndjson_stream_emits_heartbeats_before_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Regression for Cloudflare 524: the route must yield at least one
    heartbeat byte BEFORE the slow translate call has a chance to complete.
    If the very first byte we send is the final payload, a 100 s translate
    behind cloudflared will 524 every time.

    We force this by making the fake translate take ~2 heartbeat intervals
    and asserting the buffer contains heartbeats interleaved with the final
    payload line.
    """
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    # Tight heartbeat for a fast test; production uses 5 s.
    monkeypatch.setattr(concept_route, "_HEARTBEAT_INTERVAL_S", 0.05)

    async def slow_call(_s: str, _u: str) -> str:
        await asyncio.sleep(0.2)  # at least 4 heartbeat intervals
        return _fake_payload()

    monkeypatch.setattr(engine, "_call_claude", slow_call)

    req = concept_route.TranslateRequest.model_validate(
        {
            "tokens": [_TOKEN],
            "summary": _SUMMARY,
            "audio_hash": "deadbeefdeadbeef",
            "session_id": "stream-test",
        }
    )

    chunks: list[bytes] = []
    async for chunk in concept_route._translate_ndjson_stream(req):
        chunks.append(chunk)

    # At least one heartbeat must arrive before the payload line.
    assert len(chunks) >= 2, (
        f"expected ≥2 chunks (heartbeat + payload), got {chunks!r}"
    )
    assert chunks[0] == concept_route._HEARTBEAT_LINE, (
        f"first chunk must be a heartbeat, got {chunks[0]!r}"
    )
    # Final chunk must be parseable JSON with the real payload shape.
    final = json.loads(chunks[-1].decode("utf-8").strip())
    assert "chosen" in final, f"final chunk missing payload shape: {final!r}"


async def test_translate_ndjson_stream_cancels_inner_task_on_client_disconnect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """If the client disconnects mid-stream we don't want to keep burning
    aipaibox tokens for a response no one will read. The generator's
    ``except asyncio.CancelledError`` branch must cancel the underlying
    translate task before re-raising."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(concept_route, "_HEARTBEAT_INTERVAL_S", 0.05)

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_call(_s: str, _u: str) -> str:
        started.set()
        try:
            await asyncio.sleep(10)  # never reached
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return _fake_payload()

    monkeypatch.setattr(engine, "_call_claude", slow_call)

    req = concept_route.TranslateRequest.model_validate(
        {
            "tokens": [_TOKEN],
            "summary": _SUMMARY,
            "audio_hash": "deadbeefdeadbeef",
            "session_id": "cancel-test",
        }
    )

    gen = concept_route._translate_ndjson_stream(req)
    # Consume the initial heartbeat so the inner translate task is running.
    first = await gen.__anext__()
    assert first == concept_route._HEARTBEAT_LINE
    await started.wait()
    # Now simulate client disconnect by closing the generator.
    await gen.aclose()
    # Give the cancellation a moment to propagate.
    await asyncio.sleep(0.05)
    assert cancelled.is_set(), "inner translate task was not cancelled"
