"""/api/concept/translate route — SDK mocked."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bark_to_game.main import app
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
    data = response.json()
    assert "chosen" in data
    assert data["candidate_count"] == 2
    assert data["chosen"]["title"] in {"Pebble Storm", "Other Idea"}
    assert "style_triplet" in data
    assert "visual_recipe" in data


def test_translate_route_502_on_sdk_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
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
    assert response.status_code == 502
