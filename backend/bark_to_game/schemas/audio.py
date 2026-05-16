"""Schemas for /api/audio/* routes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenSegment(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    type: str
    pitch: str
    duration: str
    intensity: str
    contour: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str  # "yamnet" | "heuristic"


class SessionSummary(BaseModel):
    rhythm: str
    mood: str
    entropy: float = Field(ge=0.0, le=1.0)


class AnalyzeResponse(BaseModel):
    audio_hash: str
    duration_ms: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    tokens: list[TokenSegment]
    summary: SessionSummary
