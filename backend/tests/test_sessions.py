"""Session manager + /api/sessions routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bark_to_game.main import app
from bark_to_game.sessions import manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_sessions_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(manager, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(manager, "INDEX_PATH", tmp_path / "index.json")


def test_list_all_seeds_default() -> None:
    sessions = manager.list_all()
    assert any(s["id"] == "default" for s in sessions)


def test_create_and_get() -> None:
    created = manager.create(name="my session")
    assert created["name"] == "my session"
    got = manager.get(created["id"])
    assert got == created


def test_create_blank_name_auto_numbers() -> None:
    a = manager.create()
    b = manager.create()
    # default + a + b → indices 2, 3
    assert a["name"] != b["name"]
    assert a["name"].startswith("session #")


def test_create_strips_whitespace() -> None:
    s = manager.create(name="   ")
    assert s["name"].startswith("session #")


def test_route_list_includes_default() -> None:
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    ids = [s["id"] for s in data["sessions"]]
    assert "default" in ids


def test_route_create_and_get() -> None:
    response = client.post("/api/sessions", json={"name": "playtest"})
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "playtest"
    got = client.get(f"/api/sessions/{created['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "playtest"


def test_route_get_unknown_404() -> None:
    response = client.get("/api/sessions/no-such")
    assert response.status_code == 404
