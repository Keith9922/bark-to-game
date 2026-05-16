"""Tests for the /api/audio/analyze endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from bark_to_game.main import app

client = TestClient(app)


def test_analyze_route_success(short_bark_audio: bytes, force_heuristic: None) -> None:
    response = client.post(
        "/api/audio/analyze",
        files={"audio": ("bark.wav", short_bark_audio, "audio/wav")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audio_hash" in data
    assert "tokens" in data
    assert "summary" in data
    assert isinstance(data["tokens"], list)


def test_analyze_route_rejects_empty(force_heuristic: None) -> None:
    response = client.post(
        "/api/audio/analyze",
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400


def test_analyze_route_rejects_too_large(force_heuristic: None) -> None:
    payload = b"\x00" * (11 * 1024 * 1024)
    response = client.post(
        "/api/audio/analyze",
        files={"audio": ("big.bin", payload, "application/octet-stream")},
    )
    assert response.status_code == 413


def test_cors_preflight() -> None:
    response = client.options(
        "/api/audio/analyze",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
