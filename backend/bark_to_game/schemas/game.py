"""Schemas for /api/game/* routes (async job pattern)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from bark_to_game.schemas.concept import Concept, StyleTriplet

JobStatus = Literal["pending", "running", "done", "failed", "cancelled"]

JobEventType = Literal[
    "hello",  # initial replay on SSE connect (current status + history snapshot)
    "message",  # SDK assistant message arrived
    "write",  # SDK invoked the Write tool
    "rate_limit",  # SDK forwarded a RateLimitEvent from the service
    "heartbeat",  # no other event in the past few seconds — keeps EventSource alive
    "done",  # terminal: game generated
    "failed",  # terminal: generation errored
    "cancelled",  # terminal: user cancelled
]


class GenerateRequest(BaseModel):
    concept: Concept
    style_triplet: StyleTriplet
    visual_recipe: str  # recipe name (without "recipe_" prefix or ".md")
    audio_hash: str
    session_id: str = "default"


class GenerateAccepted(BaseModel):
    """Returned immediately from POST /generate — the heavy work runs async."""

    job_id: str
    status: JobStatus
    status_url: str  # GET this to poll
    stream_url: str  # GET this as text/event-stream for live progress


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    elapsed_s: float
    game_id: str | None = None
    summary: str | None = None
    play_url: str | None = None
    error: str | None = None


class JobEvent(BaseModel):
    """Single event sent down the SSE stream for /api/game/job/{id}/stream."""

    type: JobEventType
    ts: float
    data: dict[str, Any] = Field(default_factory=dict)
