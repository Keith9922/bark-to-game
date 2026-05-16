"""Game generation (async job) + playback endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from loguru import logger

from bark_to_game.generate import jobs
from bark_to_game.generate.generator import generate
from bark_to_game.generate.jobs import JobState
from bark_to_game.history import manager as history
from bark_to_game.paths import GENERATED_GAMES_DIR
from bark_to_game.schemas.game import (
    GenerateAccepted,
    GenerateRequest,
    JobView,
)

router = APIRouter(prefix="/api/game", tags=["game"])

# Hold strong references so generation tasks aren't garbage-collected mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _style_summary(req: GenerateRequest) -> str:
    t = req.style_triplet
    return (
        f"- Art: **{t.art.name}** - {t.art.description}\n"
        f"- Mechanic: **{t.mechanic.name}** - {t.mechanic.description}\n"
        f"- Mood: **{t.mood.name}** - {t.mood.description}"
    )


def _job_view(job: JobState) -> JobView:
    return JobView(
        job_id=job.job_id,
        status=job.status,
        elapsed_s=round(job.elapsed_s(), 1),
        game_id=job.game_id,
        summary=job.summary,
        play_url=f"/api/game/{job.game_id}/play" if job.game_id else None,
        error=job.error,
    )


def _record_history(job: JobState, req: GenerateRequest, game_id: str) -> None:
    try:
        history.record(
            history.HistoryEntry(
                game_id=game_id,
                session_id=req.session_id,
                created_at=job.finished_at or job.created_at,
                title=req.concept.title,
                tagline=req.concept.tagline,
                audio_hash=req.audio_hash,
                visual_recipe=req.visual_recipe,
                art=req.style_triplet.art.name,
                mechanic=req.style_triplet.mechanic.name,
                mood=req.style_triplet.mood.name,
            )
        )
    except Exception as exc:  # history is auxiliary — never fail the job over it
        logger.warning(f"job {job.job_id}: history record failed - {exc!r}")


async def _run_job(job: JobState, req: GenerateRequest) -> None:
    job.mark_running()
    logger.info(f"job {job.job_id}: running (recipe={req.visual_recipe})")
    try:
        result = await generate(
            concept=req.concept.model_dump(),
            style_triplet_summary=_style_summary(req),
            visual_recipe_name=req.visual_recipe,
        )
        job.mark_done(game_id=result["game_id"], summary=result["summary"])
        _record_history(job, req, result["game_id"])
        logger.info(f"job {job.job_id}: done game_id={result['game_id']} ({job.elapsed_s():.0f}s)")
    except asyncio.CancelledError:
        # The DELETE endpoint cancelled us. Surface that explicitly to the client
        # instead of letting the propagating cancellation kill the FastAPI worker.
        job.mark_cancelled()
        logger.info(f"job {job.job_id}: cancelled ({job.elapsed_s():.0f}s)")
        raise
    except Exception as exc:
        job.mark_failed(str(exc))
        logger.warning(f"job {job.job_id}: failed ({job.elapsed_s():.0f}s) - {exc!r}")


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(req: GenerateRequest) -> GenerateAccepted:
    """Fire-and-forget. Client polls GET /api/game/job/{job_id} for state."""
    job = jobs.new_job()
    task = asyncio.create_task(_run_job(job, req))
    job.task = task
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return GenerateAccepted(
        job_id=job.job_id,
        status=job.status,
        status_url=f"/api/game/job/{job.job_id}",
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str) -> JobView:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job {job_id}")
    return _job_view(job)


@router.delete("/job/{job_id}")
async def cancel_job(job_id: str) -> JobView:
    """Stop an in-flight generation. Idempotent: already-finished jobs return
    their current state unchanged."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job {job_id}")
    if job.status in ("done", "failed", "cancelled"):
        return _job_view(job)

    if job.task is not None and not job.task.done():
        job.task.cancel()
    # Mark cancelled here too so a quick re-GET sees the right state even if the
    # task hasn't yielded to handle CancelledError yet.
    job.mark_cancelled()
    logger.info(f"job {job_id}: cancel requested")
    return _job_view(job)


@router.get("/{game_id}/play")
async def play_game(game_id: str) -> FileResponse:
    # Restrict to alphanumeric/hyphen to avoid path traversal.
    if not game_id.replace("-", "").isalnum():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid game id")
    path = GENERATED_GAMES_DIR / game_id / "game.html"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"game {game_id} not found")
    return FileResponse(path, media_type="text/html")
