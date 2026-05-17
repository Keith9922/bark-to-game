"""Schemas for /api/audio/* routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DetectionState = Literal["bark", "silent", "not_a_bark"]


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
    # Detection outcome — the front-end uses this to route to the right phase:
    #   "bark"       -> proceed to translate + generate
    #   "silent"     -> "we didn't hear anything"
    #   "not_a_bark" -> "we heard <detected_class>, please bark at the mic"
    detection: DetectionState = "bark"
    # YAMNet display name of the dominant non-dog class when detection
    # is "not_a_bark" (e.g. "Speech"). Empty otherwise.
    detected_class: str = ""
    # How many segments YAMNet rejected as non-dog. Useful for diagnostics.
    rejected_segment_count: int = 0
