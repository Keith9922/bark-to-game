"""Schemas for /api/concept/* routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bark_to_game.schemas.audio import SessionSummary, TokenSegment


class TranslateRequest(BaseModel):
    tokens: list[TokenSegment]
    summary: SessionSummary
    audio_hash: str
    session_id: str = "default"


class Concept(BaseModel):
    title: str
    tagline: str
    player: str
    core_mechanic: str
    win_condition: str
    fail_condition: str
    # Playability-rubric fields (added in feat/playability-overhaul). Optional
    # with empty-string defaults so the schema is forgiving if the model
    # occasionally omits one — the generator just renders nothing for that
    # slot in CLAUDE.md rather than crashing.
    onboarding_hint: str = ""
    escalation_moment: str = ""
    replay_hook: str = ""
    visual_summary: str
    audio_summary: str


class StyleCardRef(BaseModel):
    name: str
    description: str


class StyleTriplet(BaseModel):
    art: StyleCardRef
    mechanic: StyleCardRef
    mood: StyleCardRef


# Discrete bands derived from the original bark — feed concrete numbers
# downstream to the generator so the same mechanic plays differently for a
# frantic-staccato bark vs a long-spaced one.
Tempo = Literal["slow", "medium", "fast", "frantic"]
Density = Literal["sparse", "moderate", "dense"]
Intensity = Literal["gentle", "firm", "harsh"]
Variability = Literal["steady", "shifting", "wild"]


class GameParams(BaseModel):
    """Audio-derived gameplay knobs. The translate layer derives these from
    the bark tokens + session summary and passes them through to the generator
    so the same mechanic actually plays differently for different barks.
    """

    tempo: Tempo
    density: Density
    intensity: Intensity
    variability: Variability

    # Concrete numbers the generator's CLAUDE.md spec can paste directly:
    spawn_interval_ms: int  # base ms between spawns / beats / waves
    max_concurrent: int  # cap on simultaneous active entities
    escalation_per_min: float  # multiplier per minute (e.g. 1.5 = +50%/min)
    randomness_pct: int  # ±% jitter around base values


class TranslateResponse(BaseModel):
    chosen: Concept
    chosen_probability: float = Field(ge=0.0, le=1.0)
    chosen_score: float
    candidate_count: int
    style_triplet: StyleTriplet
    visual_recipe: str
    game_params: GameParams
    avoided_summaries: list[str]
