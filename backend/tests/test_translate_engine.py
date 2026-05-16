"""Translate engine: parse + select, with the SDK call mocked."""

from __future__ import annotations

import json
from typing import Any

import pytest

from bark_to_game.translate import archive, engine

SAMPLE_TOKENS: list[dict[str, Any]] = [
    {
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
]

SAMPLE_SUMMARY: dict[str, Any] = {"rhythm": "STACCATO", "mood": "AGITATED", "entropy": 0.4}


def _fake_response(titles: list[str]) -> str:
    payload = {
        "candidates": [
            {
                "probability": round(1.0 / len(titles), 3),
                "concept": {
                    "title": title,
                    "tagline": f"{title} - a tagline",
                    "player": "you",
                    "core_mechanic": "test mechanic",
                    "win_condition": "win",
                    "fail_condition": "lose",
                    "visual_summary": "visuals",
                    "audio_summary": "audio",
                },
            }
            for title in titles
        ]
    }
    return json.dumps(payload)


def test_parse_candidates_round_trip() -> None:
    raw = _fake_response(["A", "B", "C"])
    candidates = engine.parse_candidates(raw)
    assert len(candidates) == 3
    assert candidates[0]["concept"]["title"] == "A"


def test_parse_candidates_strips_fences() -> None:
    raw = "```json\n" + _fake_response(["A"]) + "\n```"
    assert len(engine.parse_candidates(raw)) == 1


def test_parse_candidates_rejects_empty() -> None:
    with pytest.raises(ValueError):
        engine.parse_candidates(json.dumps({"candidates": []}))


def test_select_prefers_diverse_when_history_present() -> None:
    raw = _fake_response(["Brand New Idea", "Older Concept Lookalike"])
    candidates = engine.parse_candidates(raw)
    chosen, _score = engine._select(candidates, recent=["Older Concept Lookalike - a tagline"])
    assert chosen["concept"]["title"] == "Brand New Idea"


async def test_translate_full_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)

    async def fake_call(_system: str, _user: str) -> str:
        return _fake_response(["Concept X", "Concept Y", "Concept Z", "Concept W", "Concept V"])

    monkeypatch.setattr(engine, "_call_claude", fake_call)

    result = await engine.translate(
        tokens=SAMPLE_TOKENS,
        summary=SAMPLE_SUMMARY,
        audio_hash="abcd1234abcd1234",
        session_id="test-session",
    )
    assert result["chosen"]["title"] in {f"Concept {x}" for x in "XYZWV"}
    assert len(result["candidates"]) == 5
    assert result["style_triplet"]["art"]["name"]
    # archive should now contain the chosen entry
    entries = archive.load("test-session")
    assert len(entries) == 1
