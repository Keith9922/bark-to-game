"""Audio analysis + original-recording playback."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from loguru import logger

from bark_to_game import paths
from bark_to_game.audio.pipeline import analyze
from bark_to_game.schemas.audio import AnalyzeResponse

router = APIRouter(prefix="/api/audio", tags=["audio"])

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/analyze")
async def analyze_audio(audio: Annotated[UploadFile, File()]) -> AnalyzeResponse:
    """Accept a recorded WAV/WebM clip, return compound token sequence.

    On success, persist the raw upload at `data/audio/{audio_hash}.wav` so it
    can later be played back from the history panel. Persistence is best-effort
    — a failed disk write does not block returning the analysis to the caller.
    """
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

    try:
        paths.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        (paths.AUDIO_DIR / f"{result['audio_hash']}.wav").write_bytes(audio_bytes)
    except OSError as exc:
        logger.warning(f"could not persist audio {result['audio_hash']}: {exc!r}")

    return AnalyzeResponse(**result)


@router.get("/{audio_hash}/play")
async def play_audio(audio_hash: str) -> FileResponse:
    """Serve the original recording for a hash (for history-panel playback)."""
    if not audio_hash.isalnum():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid audio hash")
    path = paths.AUDIO_DIR / f"{audio_hash}.wav"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"audio {audio_hash} not found")
    return FileResponse(path, media_type="audio/wav")
