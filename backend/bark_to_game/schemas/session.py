"""Schemas for /api/sessions routes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionMetaView(BaseModel):
    id: str
    name: str
    created_at: float


class SessionsResponse(BaseModel):
    sessions: list[SessionMetaView]


class CreateSessionRequest(BaseModel):
    name: str | None = Field(default=None, max_length=64)
