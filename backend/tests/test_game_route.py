"""/api/game/* tests — generator mocked, async job lifecycle exercised."""

from __future__ import annotations

import asyncio
from pathlib import Path
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


def _request_body(visual_recipe: str = "pixel_crt") -> dict[str, Any]:
    return {
        "concept": _CONCEPT,
        "style_triplet": _STYLE_TRIPLET,
        "visual_recipe": visual_recipe,
        "audio_hash": "abcd1234abcd1234",
        "session_id": "route-test",
    }


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    jobs.reset_for_tests()


def _poll(job_id: str, max_attempts: int = 50) -> dict[str, Any]:
    """Spin the event loop until the background task completes."""
    for _ in range(max_attempts):
        response = client.get(f"/api/game/job/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in {"done", "failed"}:
            return data
        # asyncio.sleep yields back to the event loop so the background task can advance.
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.02))
    raise AssertionError(f"job {job_id} did not terminate")


def test_generate_returns_202_and_job_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_generate(**_: Any) -> generator.GenerationResult:
        return generator.GenerationResult(
            game_id="deadbeef0001",
            game_path=str(tmp_path / "deadbeef0001" / "game.html"),
            summary="fake summary",
            cwd=str(tmp_path / "deadbeef0001"),
        )

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", fake_generate)

    response = client.post("/api/game/generate", json=_request_body())
    assert response.status_code == 202, response.text
    data = response.json()
    assert "job_id" in data
    assert data["status"] in {"pending", "running"}
    assert data["status_url"] == f"/api/game/job/{data['job_id']}"

    final = _poll(data["job_id"])
    assert final["status"] == "done"
    assert final["game_id"] == "deadbeef0001"
    assert final["summary"] == "fake summary"
    assert final["play_url"] == "/api/game/deadbeef0001/play"


def test_generate_job_records_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def boom(**_: Any) -> generator.GenerationResult:
        raise RuntimeError("simulated SDK outage")

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", boom)

    response = client.post("/api/game/generate", json=_request_body())
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    final = _poll(job_id)
    assert final["status"] == "failed"
    assert "simulated SDK outage" in (final["error"] or "")
    assert final["play_url"] is None


def test_get_job_404_for_unknown_id() -> None:
    response = client.get("/api/game/job/nope")
    assert response.status_code == 404


def test_play_route_serves_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "GENERATED_GAMES_DIR", tmp_path)

    game_dir = tmp_path / "abc123"
    game_dir.mkdir(parents=True)
    (game_dir / "game.html").write_text("<html>hi</html>")

    response = client.get("/api/game/abc123/play")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<html>hi</html>"


def test_play_route_404_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "GENERATED_GAMES_DIR", tmp_path)
    response = client.get("/api/game/notthere/play")
    assert response.status_code == 404


def test_play_route_rejects_path_traversal() -> None:
    response = client.get("/api/game/..%2Fetc/play")
    assert response.status_code in (400, 404)
