"""Health endpoint smoke test."""

from fastapi.testclient import TestClient

from bark_to_game import __version__
from bark_to_game.main import app

client = TestClient(app)


def test_health_returns_ok_and_version() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
