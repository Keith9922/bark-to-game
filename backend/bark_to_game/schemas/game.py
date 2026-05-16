"""Schemas for /api/game/* routes (async job pattern)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bark_to_game.schemas.concept import Concept, StyleTriplet

JobStatus = Literal["pending", "running", "done", "failed"]


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


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    elapsed_s: float
    game_id: str | None = None
    summary: str | None = None
    play_url: str | None = None
    error: str | None = None
