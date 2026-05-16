"""Schemas for /api/concept/* routes."""

from __future__ import annotations

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
    visual_summary: str
    audio_summary: str


class StyleCardRef(BaseModel):
    name: str
    description: str


class StyleTriplet(BaseModel):
    art: StyleCardRef
    mechanic: StyleCardRef
    mood: StyleCardRef


class TranslateResponse(BaseModel):
    chosen: Concept
    chosen_probability: float = Field(ge=0.0, le=1.0)
    chosen_score: float
    candidate_count: int
    style_triplet: StyleTriplet
    visual_recipe: str
    avoided_summaries: list[str]
