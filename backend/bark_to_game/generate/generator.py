"""Generator dispatcher — routes to ``_api_backend`` or ``_sdk_backend``.

Public surface (used by routes/game.py and tests):
- :func:`generate` — entry point; backend chosen by ``BARK_GENERATOR_MODE``
- :class:`GenerationResult` — typed result shape
- :class:`RateLimitedError` / :class:`GenerationStalledError` — failure modes
  the HTTP layer surfaces verbatim to the user (both backends raise the same
  types so the route is backend-agnostic)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from bark_to_game import settings
from bark_to_game.generate._common import (
    GenerationResult,
    GenerationStalledError,
    GenerationTruncatedError,
    RateLimitedError,
)
from bark_to_game.schemas.game import JobEvent

__all__ = [
    "GenerationResult",
    "GenerationStalledError",
    "GenerationTruncatedError",
    "RateLimitedError",
    "generate",
]


async def generate(
    concept: dict[str, Any],
    style_triplet_summary: str,
    visual_recipe_name: str,
    *,
    game_params: dict[str, Any] | None = None,
    on_start: Callable[[str], None] | None = None,
    publish: Callable[[JobEvent], None] | None = None,
) -> GenerationResult:
    """Dispatch to the configured backend.

    ``game_params`` are the audio-derived gameplay knobs (tempo, density,
    intensity, variability + concrete spawn / concurrency / escalation
    numbers). Both backends render them into the CLAUDE.md spec so the
    bark actually drives gameplay pacing — not just decoration.

    ``on_start`` is invoked with the absolute per-game cwd as soon as it's
    created — the HTTP cancel handler uses this to find and SIGKILL any
    SDK subprocess that didn't self-clean (no-op for the API backend, which
    spawns no subprocess).

    ``publish`` is a non-blocking event sink for the SSE stream.
    """
    if settings.GENERATOR_MODE == "api":
        from bark_to_game.generate import _api_backend

        backend = _api_backend.generate_via_api
        logger.debug(f"generator: routing to API backend (model={settings.API_MODEL})")
    else:
        from bark_to_game.generate import _sdk_backend

        backend = _sdk_backend.generate_via_sdk
        logger.debug("generator: routing to SDK backend")

    return await backend(
        concept=concept,
        style_triplet_summary=style_triplet_summary,
        visual_recipe_name=visual_recipe_name,
        game_params=game_params,
        on_start=on_start,
        publish=publish,
    )
