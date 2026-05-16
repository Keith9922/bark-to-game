"""History manager + route tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bark_to_game import paths
from bark_to_game.history import manager
from bark_to_game.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_data_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    audio_dir = tmp_path / "audio"
    monkeypatch.setattr(paths, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(paths, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(manager, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(manager, "AUDIO_DIR", audio_dir)


def _entry(suffix: str, session: str = "default") -> manager.HistoryEntry:
    return manager.HistoryEntry(
        game_id=f"game{suffix}",
        session_id=session,
        created_at=time.time(),
        title=f"Title {suffix}",
        tagline=f"Tagline {suffix}",
        audio_hash=f"hash{suffix}",
        visual_recipe="pixel_crt",
        art="cubism",
        mechanic="catch",
        mood="serene",
    )


def test_empty_session_returns_empty() -> None:
    assert manager.list_for_session("never") == []


def test_record_and_list_roundtrip() -> None:
    manager.record(_entry("A"))
    manager.record(_entry("B"))
    entries = manager.list_for_session("default")
    assert len(entries) == 2
    titles = {e.title for e in entries}
    assert titles == {"Title A", "Title B"}


def test_list_is_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    older = manager.HistoryEntry(
        game_id="old",
        session_id="default",
        created_at=100.0,
        title="Old",
        tagline="t",
        audio_hash="h1",
        visual_recipe="pixel_crt",
        art="cubism",
        mechanic="catch",
        mood="serene",
    )
    newer = manager.HistoryEntry(
        game_id="new",
        session_id="default",
        created_at=200.0,
        title="New",
        tagline="t",
        audio_hash="h2",
        visual_recipe="pixel_crt",
        art="cubism",
        mechanic="catch",
        mood="serene",
    )
    manager.record(older)
    manager.record(newer)
    entries = manager.list_for_session("default")
    assert entries[0].game_id == "new"
    assert entries[1].game_id == "old"


def test_record_caps_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "MAX_HISTORY_PER_SESSION", 3)
    for i in range(7):
        manager.record(
            manager.HistoryEntry(
                game_id=f"g{i}",
                session_id="default",
                created_at=float(i),
                title=f"t{i}",
                tagline="x",
                audio_hash=f"h{i}",
                visual_recipe="r",
                art="a",
                mechanic="m",
                mood="o",
            )
        )
    entries = manager.list_for_session("default")
    assert len(entries) == 3
    # Newest 3 retained
    assert {e.game_id for e in entries} == {"g4", "g5", "g6"}


def test_record_isolates_sessions() -> None:
    manager.record(_entry("X", session="alpha"))
    manager.record(_entry("Y", session="beta"))
    assert [e.game_id for e in manager.list_for_session("alpha")] == ["gameX"]
    assert [e.game_id for e in manager.list_for_session("beta")] == ["gameY"]


def test_has_audio_returns_true_when_file_present() -> None:
    paths.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (paths.AUDIO_DIR / "abcd.wav").write_bytes(b"RIFFfakewavbody")
    assert manager.has_audio("abcd")
    assert not manager.has_audio("nope")


def test_route_returns_empty_for_fresh_session() -> None:
    response = client.get("/api/history?session_id=fresh")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "fresh"
    assert data["entries"] == []


def test_route_lists_recorded_entries() -> None:
    manager.record(_entry("R1"))
    response = client.get("/api/history?session_id=default")
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["title"] == "Title R1"
    assert entry["play_url"] == "/api/game/gameR1/play"
    # audio file isn't on disk → audio_url is None, has_audio False
    assert entry["has_audio"] is False
    assert entry["audio_url"] is None


def test_route_marks_audio_present_when_file_exists() -> None:
    paths.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (paths.AUDIO_DIR / "hashR2.wav").write_bytes(b"x")
    manager.record(_entry("R2"))
    response = client.get("/api/history?session_id=default")
    entry = response.json()["entries"][0]
    assert entry["has_audio"] is True
    assert entry["audio_url"] == "/api/audio/hashR2/play"


def test_audio_play_route_serves_wav() -> None:
    paths.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (paths.AUDIO_DIR / "feed.wav").write_bytes(b"RIFFfakewav")
    response = client.get("/api/audio/feed/play")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.content == b"RIFFfakewav"


def test_audio_play_route_404_unknown() -> None:
    response = client.get("/api/audio/nosuch/play")
    assert response.status_code == 404


def test_audio_play_route_rejects_invalid_hash() -> None:
    response = client.get("/api/audio/..%2Fetc/play")
    assert response.status_code in (400, 404)
