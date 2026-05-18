"""/api/game/* tests — generator mocked, async job lifecycle exercised."""

from __future__ import annotations

import asyncio
import json
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
_GAME_PARAMS = {
    "tempo": "medium",
    "density": "moderate",
    "intensity": "firm",
    "variability": "shifting",
    "spawn_interval_ms": 1000,
    "max_concurrent": 8,
    "escalation_per_min": 1.35,
    "randomness_pct": 30,
}


def _request_body(visual_recipe: str = "pixel_crt") -> dict[str, Any]:
    return {
        "concept": _CONCEPT,
        "style_triplet": _STYLE_TRIPLET,
        "visual_recipe": visual_recipe,
        "game_params": _GAME_PARAMS,
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
        if data["status"] in {"done", "failed", "cancelled"}:
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


def test_cancel_in_flight_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """A still-running job can be cancelled; subsequent polls report 'cancelled'."""

    async def slow_generate(**_: Any) -> generator.GenerationResult:
        await asyncio.sleep(10)  # long enough that DELETE catches it
        raise AssertionError("should have been cancelled before reaching here")

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", slow_generate)

    start = client.post("/api/game/generate", json=_request_body())
    assert start.status_code == 202
    job_id = start.json()["job_id"]

    # Yield once so the task transitions to 'running'.
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))

    cancel = client.delete(f"/api/game/job/{job_id}")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    # Subsequent GET is consistent.
    status_check = client.get(f"/api/game/job/{job_id}").json()
    assert status_check["status"] == "cancelled"
    assert status_check["play_url"] is None


def test_cancel_already_done_job_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fast(**_: Any) -> generator.GenerationResult:
        return generator.GenerationResult(game_id="abc", game_path="x", summary="s", cwd="d")

    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(game_route, "generate", fast)

    start = client.post("/api/game/generate", json=_request_body())
    job_id = start.json()["job_id"]
    _poll(job_id)  # let it finish

    cancel = client.delete(f"/api/game/job/{job_id}")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "done"


def test_cancel_unknown_job_404() -> None:
    response = client.delete("/api/game/job/nope")
    assert response.status_code == 404


def _wire_showcase_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path, Path]:
    """Point HISTORY_DIR / AUDIO_DIR / GENERATED_GAMES_DIR at tmp_path subdirs."""
    history_dir = tmp_path / "history"
    audio_dir = tmp_path / "audio"
    games_dir = tmp_path / "generated-games"
    history_dir.mkdir()
    audio_dir.mkdir()
    games_dir.mkdir()

    from bark_to_game import paths
    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(paths, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(paths, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(game_route, "GENERATED_GAMES_DIR", games_dir)
    return history_dir, audio_dir, games_dir


def _write_game(games_dir: Path, game_id: str, summary: str | None = None) -> None:
    game_dir = games_dir / game_id
    game_dir.mkdir(parents=True)
    (game_dir / "game.html").write_text(f"<!-- {game_id} -->")
    if summary is not None:
        (game_dir / "SUMMARY.md").write_text(summary)


def test_showcase_merges_history_and_orphan_games(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    history_dir, audio_dir, games_dir = _wire_showcase_dirs(monkeypatch, tmp_path)

    # History entry with everything wired up (audio file exists)
    audio_hash = "feedbeef" * 8
    (audio_dir / f"{audio_hash}.wav").write_bytes(b"RIFF...")
    _write_game(games_dir, "game-with-history")
    (history_dir / "session-a.json").write_text(
        json.dumps(
            [
                {
                    "game_id": "game-with-history",
                    "title": "Bark Quest",
                    "tagline": "a barky journey",
                    "art": "cubism",
                    "mechanic": "catch",
                    "mood": "serene",
                    "visual_recipe": "pixel_crt",
                    "audio_hash": audio_hash,
                    "created_at": 1000.0,
                }
            ]
        )
    )

    # Filesystem-only orphan with a parsable SUMMARY.md
    _write_game(games_dir, "orphan-game", summary="**ORPHAN** — no history index entry")

    response = client.get("/api/game/showcase/all")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2

    by_id = {it["game_id"]: it for it in items}

    history_item = by_id["game-with-history"]
    assert history_item["has_history"] is True
    assert history_item["title"] == "Bark Quest"
    assert history_item["tagline"] == "a barky journey"
    assert history_item["audio_url"] == f"/api/audio/{audio_hash}/play"
    assert history_item["play_url"] == "/api/game/game-with-history/play"

    orphan_item = by_id["orphan-game"]
    assert orphan_item["has_history"] is False
    assert orphan_item["title"] == "ORPHAN"
    assert orphan_item["tagline"] == "no history index entry"
    assert orphan_item["audio_url"] is None


def test_showcase_omits_history_rows_when_game_html_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    history_dir, _audio_dir, games_dir = _wire_showcase_dirs(monkeypatch, tmp_path)

    # Game on disk → kept
    _write_game(games_dir, "kept")
    # History row for a vanished game (e.g. cancelled job) → hidden
    (history_dir / "s.json").write_text(
        json.dumps(
            [
                {"game_id": "kept", "title": "Kept", "created_at": 2.0},
                {"game_id": "vanished", "title": "Vanished", "created_at": 1.0},
            ]
        )
    )

    response = client.get("/api/game/showcase/all")
    assert response.status_code == 200
    ids = [it["game_id"] for it in response.json()["items"]]
    assert ids == ["kept"]


def test_showcase_omits_audio_url_when_wav_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    history_dir, _audio_dir, games_dir = _wire_showcase_dirs(monkeypatch, tmp_path)
    _write_game(games_dir, "no-audio")
    (history_dir / "s.json").write_text(
        json.dumps(
            [
                {
                    "game_id": "no-audio",
                    "title": "Silent",
                    "audio_hash": "missingaudio" * 4,
                    "created_at": 1.0,
                }
            ]
        )
    )

    response = client.get("/api/game/showcase/all")
    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item["audio_url"] is None


def test_showcase_sorts_newest_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    history_dir, _audio_dir, games_dir = _wire_showcase_dirs(monkeypatch, tmp_path)
    for game_id, ts in (("old", 100.0), ("new", 200.0), ("mid", 150.0)):
        _write_game(games_dir, game_id)
    (history_dir / "s.json").write_text(
        json.dumps(
            [
                {"game_id": "old", "title": "Old", "created_at": 100.0},
                {"game_id": "new", "title": "New", "created_at": 200.0},
                {"game_id": "mid", "title": "Mid", "created_at": 150.0},
            ]
        )
    )

    response = client.get("/api/game/showcase/all")
    assert [it["game_id"] for it in response.json()["items"]] == ["new", "mid", "old"]


def test_showcase_empty_when_no_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _wire_showcase_dirs(monkeypatch, tmp_path)
    response = client.get("/api/game/showcase/all")
    assert response.status_code == 200
    assert response.json() == {"items": []}
