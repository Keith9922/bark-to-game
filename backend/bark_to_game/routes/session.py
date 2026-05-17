"""Session listing + creation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from bark_to_game.schemas.session import (
    CreateSessionRequest,
    SessionMetaView,
    SessionsResponse,
)
from bark_to_game.sessions import manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _view(meta: manager.SessionMeta) -> SessionMetaView:
    return SessionMetaView(id=meta["id"], name=meta["name"], created_at=meta["created_at"])


@router.get("")
async def list_sessions() -> SessionsResponse:
    return SessionsResponse(sessions=[_view(s) for s in manager.list_all()])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(req: CreateSessionRequest) -> SessionMetaView:
    created = manager.create(name=req.name)
    return _view(created)


@router.get("/{session_id}")
async def get_session(session_id: str) -> SessionMetaView:
    meta = manager.get(session_id)
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown session {session_id}")
    return _view(meta)
