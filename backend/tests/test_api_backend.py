"""Tests for the direct-API generator backend.

Mocks httpx via a custom transport so we never touch the network. Validates:
  - happy path: streamed text → html+summary parsing → files on disk
  - rate-limit: HTTP 429 → RateLimitedError
  - error block in SSE → RuntimeError
  - missing API key → RuntimeError
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from bark_to_game import settings
from bark_to_game.generate import _api_backend, _common
from bark_to_game.schemas.game import JobEvent

_CONCEPT = {
    "title": "Test",
    "tagline": "t",
    "player": "p",
    "core_mechanic": "m",
    "win_condition": "w",
    "fail_condition": "l",
    "visual_summary": "v",
    "audio_summary": "a",
}


def _sse_body(text: str) -> bytes:
    """Build a minimal Anthropic-format SSE response that delivers ``text``."""
    events = [
        {"type": "message_start", "message": {"id": "msg", "role": "assistant"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
        {"type": "message_stop"},
    ]
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_client_with(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Replace httpx.AsyncClient so the production code's instantiation
    transparently routes through ``handler`` instead of the network. We
    capture the real class once so the lambda doesn't recurse into itself."""
    transport = httpx.MockTransport(handler)

    def factory(**kw: Any) -> httpx.AsyncClient:
        return _REAL_ASYNC_CLIENT(transport=transport, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.fixture
def patch_recipes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the generator at a tmp recipes + games dir with a fake recipe."""
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    (recipes_dir / "recipe_pixel_crt.md").write_text("# pixel\npalette: #fff")
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    import bark_to_game.paths as paths

    monkeypatch.setattr(paths, "VISUAL_RECIPES_DIR", recipes_dir)
    monkeypatch.setattr(paths, "GENERATED_GAMES_DIR", games_dir)
    # _common reads these as module-level constants captured at import time.
    monkeypatch.setattr(_common, "VISUAL_RECIPES_DIR", recipes_dir)
    monkeypatch.setattr(_common, "GENERATED_GAMES_DIR", games_dir)


@pytest.fixture
def patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "API_KEY", "sk-test")
    monkeypatch.setattr(settings, "API_BASE_URL", "https://test.example.com")
    monkeypatch.setattr(settings, "API_MODEL", "claude-opus-4-7")


async def test_api_generate_happy_path(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    body = (
        "Here is the game:\n\n"
        "```html\n<!DOCTYPE html><html><body>X</body></html>\n```\n\n"
        "```markdown\nA tiny test game.\n```\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "sk-test"
        payload = json.loads(request.content)
        assert payload["model"] == "claude-opus-4-7"
        assert payload["stream"] is True
        return httpx.Response(200, content=_sse_body(body))

    _patch_client_with(monkeypatch, handler)

    events: list[JobEvent] = []
    cwd: list[str] = []
    result = await _api_backend.generate_via_api(
        concept=_CONCEPT,
        style_triplet_summary="art x mechanic x mood",
        visual_recipe_name="pixel_crt",
        on_start=cwd.append,
        publish=events.append,
    )

    assert Path(result["game_path"]).read_text() == "<!DOCTYPE html><html><body>X</body></html>"
    assert result["summary"] == "A tiny test game."
    assert len(cwd) == 1 and cwd[0] == result["cwd"]
    assert any(e.type == "write" for e in events)


async def test_api_generate_rate_limited(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            content=b'{"error":{"type":"rate_limit","message":"too many"}}',
            headers={"retry-after": "60"},
        )

    _patch_client_with(monkeypatch, handler)

    with pytest.raises(_common.RateLimitedError) as exc:
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )
    assert exc.value.resets_at is not None  # retry-after parsed


async def test_api_generate_missing_key(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None
) -> None:
    monkeypatch.setattr(settings, "API_KEY", None)
    with pytest.raises(RuntimeError, match="BARK_API_KEY"):
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )


async def test_api_generate_overloaded_error_in_stream(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    err_body = (
        b'event: error\n'
        b'data: {"type":"error","error":{"type":"overloaded_error","message":"busy"}}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=err_body)

    _patch_client_with(monkeypatch, handler)

    with pytest.raises(_common.RateLimitedError, match="overloaded"):
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )


async def test_api_generate_missing_html_block(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse_body("I refuse to output code."))

    _patch_client_with(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="did not contain"):
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )
