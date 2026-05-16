"""SSE stream + improved cancel tests for /api/game/job/{id}."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bark_to_game.generate import generator, jobs
from bark_to_game.main import app

client = TestClient(app)


_CONCEPT = {
    "title": "Test Game",
    "tagline": "A test",
    "player": "p",
    "core_mechanic": "m",
    "win_condition": "w",
    "fail_condition": "l",
    "visual_summary": "v",
    "audio_summary": "a",
}
_STYLE_TRIPLET = {
    "art": {"name": "cubism", "description": "x"},
    "mechanic": {"name": "catch", "description": "y"},
    "mood": {"name": "serene", "description": "z"},
}


def _request_body() -> dict[str, Any]:
    return {
        "concept": _CONCEPT,
        "style_triplet": _STYLE_TRIPLET,
        "visual_recipe": "pixel_crt",
        "audio_hash": "abcd1234abcd1234",
        "session_id": "stream-test",
    }


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    jobs.reset_for_tests()


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """Tiny SSE parser: returns a list of {type, payload} dicts where payload
    is the JobEvent's ``data`` field (the nested per-event payload)."""
    out: list[dict[str, Any]] = []
    event_name = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            event_name = line[len("event: "):]
        elif line.startswith("data: "):
            full = json.loads(line[len("data: "):])
            out.append({"type": event_name, "payload": full.get("data", {})})
            event_name = ""
    return out


def test_generate_response_includes_stream_url() -> None:
    async def fast(**_: Any) -> generator.GenerationResult:
        return generator.GenerationResult(
            game_id="abc123def456", game_path="x", summary="s", cwd="d"
        )

    from bark_to_game.routes import game as game_route

    # monkeypatch via the module reference held by the route
    original = game_route.generate
    game_route.generate = fast  # type: ignore[assignment]
    try:
        response = client.post("/api/game/generate", json=_request_body())
        assert response.status_code == 202
        body = response.json()
        assert body["stream_url"] == f"/api/game/job/{body['job_id']}/stream"
    finally:
        game_route.generate = original  # type: ignore[assignment]


def test_stream_replays_terminal_state_for_finished_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """A late connector to the stream gets hello + terminal frame, then closes."""

    async def fast(**_: Any) -> generator.GenerationResult:
        return generator.GenerationResult(
            game_id="abcdef012345", game_path="x", summary="quick game", cwd="d"
        )

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", fast)

    started = client.post("/api/game/generate", json=_request_body())
    job_id = started.json()["job_id"]

    # Spin until done.
    for _ in range(50):
        check = client.get(f"/api/game/job/{job_id}").json()
        if check["status"] in {"done", "failed", "cancelled"}:
            break
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.02))
    assert check["status"] == "done"

    response = client.get(f"/api/game/job/{job_id}/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _parse_sse(response.text)
    types_seen = [f["type"] for f in frames]
    assert types_seen[0] == "hello"
    assert "done" in types_seen
    done_frame = next(f for f in frames if f["type"] == "done")
    assert done_frame["payload"]["game_id"] == "abcdef012345"
    assert done_frame["payload"]["play_url"] == "/api/game/abcdef012345/play"


def test_stream_404_for_unknown_job() -> None:
    response = client.get("/api/game/job/nope/stream")
    assert response.status_code == 404


def test_cancel_publishes_terminal_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """After DELETE, the SSE stream produces a 'cancelled' terminal frame."""

    async def slow(**_: Any) -> generator.GenerationResult:
        await asyncio.sleep(10)
        raise AssertionError("should have been cancelled")

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", slow)

    started = client.post("/api/game/generate", json=_request_body())
    job_id = started.json()["job_id"]
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))

    cancel = client.delete(f"/api/game/job/{job_id}")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    response = client.get(f"/api/game/job/{job_id}/stream")
    frames = _parse_sse(response.text)
    types_seen = [f["type"] for f in frames]
    assert types_seen[0] == "hello"
    assert "cancelled" in types_seen
