"""Schemas for /api/history routes."""

from __future__ import annotations

from pydantic import BaseModel


class HistoryEntryView(BaseModel):
    game_id: str
    session_id: str
    created_at: float
    title: str
    tagline: str
    audio_hash: str
    visual_recipe: str
    art: str
    mechanic: str
    mood: str
    has_audio: bool
    play_url: str  # /api/game/{game_id}/play
    audio_url: str | None  # /api/audio/{hash}/play if recording is on disk


class HistoryResponse(BaseModel):
    session_id: str
    entries: list[HistoryEntryView]
