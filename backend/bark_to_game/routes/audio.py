"""Audio analysis endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from bark_to_game.audio.pipeline import analyze
from bark_to_game.schemas.audio import AnalyzeResponse

router = APIRouter(prefix="/api/audio", tags=["audio"])

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/analyze")
async def analyze_audio(audio: Annotated[UploadFile, File()]) -> AnalyzeResponse:
    """Accept a recorded WAV/WebM clip, return compound token sequence."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty audio file")
    if len(audio_bytes) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"audio too large (max {MAX_BYTES // 1024 // 1024} MB)",
        )

    try:
        result = analyze(audio_bytes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return AnalyzeResponse(**result)
