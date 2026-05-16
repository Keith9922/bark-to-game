"""Game generation (async job) + playback endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from loguru import logger

from bark_to_game.generate import jobs
from bark_to_game.generate.generator import generate
from bark_to_game.generate.jobs import JobState
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
        logger.info(f"job {job.job_id}: done game_id={result['game_id']} ({job.elapsed_s():.0f}s)")
    except Exception as exc:
        job.mark_failed(str(exc))
        logger.warning(f"job {job.job_id}: failed ({job.elapsed_s():.0f}s) - {exc!r}")


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(req: GenerateRequest) -> GenerateAccepted:
    """Fire-and-forget. Client polls GET /api/game/job/{job_id} for state."""
    job = jobs.new_job()
    task = asyncio.create_task(_run_job(job, req))
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


@router.get("/{game_id}/play")
async def play_game(game_id: str) -> FileResponse:
    # Restrict to alphanumeric/hyphen to avoid path traversal.
    if not game_id.replace("-", "").isalnum():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid game id")
    path = GENERATED_GAMES_DIR / game_id / "game.html"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"game {game_id} not found")
    return FileResponse(path, media_type="text/html")
