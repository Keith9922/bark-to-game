"""History listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from bark_to_game.history import manager
from bark_to_game.schemas.history import HistoryEntryView, HistoryResponse

router = APIRouter(prefix="/api/history", tags=["history"])


def _to_view(entry: manager.HistoryEntry) -> HistoryEntryView:
    audio_present = manager.has_audio(entry.audio_hash) if entry.audio_hash else False
    return HistoryEntryView(
        game_id=entry.game_id,
        session_id=entry.session_id,
        created_at=entry.created_at,
        title=entry.title,
        tagline=entry.tagline,
        audio_hash=entry.audio_hash,
        visual_recipe=entry.visual_recipe,
        art=entry.art,
        mechanic=entry.mechanic,
        mood=entry.mood,
        has_audio=audio_present,
        play_url=f"/api/game/{entry.game_id}/play",
        audio_url=f"/api/audio/{entry.audio_hash}/play" if audio_present else None,
    )


@router.get("")
async def list_history(session_id: str = "default") -> HistoryResponse:
    entries = [_to_view(e) for e in manager.list_for_session(session_id)]
    return HistoryResponse(session_id=session_id, entries=entries)
