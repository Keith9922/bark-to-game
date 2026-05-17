"""Game generation (async job) + playback + SSE event stream."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

import psutil
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from bark_to_game.generate import jobs
from bark_to_game.generate.generator import (
    GenerationStalledError,
    RateLimitedError,
    generate,
)
from bark_to_game.generate.jobs import JobState
from bark_to_game.history import manager as history
from bark_to_game.paths import GENERATED_GAMES_DIR
from bark_to_game.schemas.game import (
    GenerateAccepted,
    GenerateRequest,
    JobEvent,
    JobView,
)
from bark_to_game.sessions import manager as sessions

router = APIRouter(prefix="/api/game", tags=["game"])

# Hold strong references so generation tasks aren't garbage-collected mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()

_TERMINAL_STATUSES = ("done", "failed", "cancelled")

# How long to wait for the SDK to drain after task.cancel() before we
# resort to SIGKILL'ing the subprocess directly. The SDK's own close()
# path includes a 5s graceful + 5s SIGTERM window, but its async cleanup
# is re-interrupted by the outer CancelledError before reaching them.
_CANCEL_GRACE_S = 3.0


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


def _terminal_event(job: JobState) -> JobEvent:
    return JobEvent(
        type=job.status,  # type: ignore[arg-type]
        ts=time.time(),
        data={
            "game_id": job.game_id,
            "summary": job.summary,
            "play_url": f"/api/game/{job.game_id}/play" if job.game_id else None,
            "error": job.error,
            "elapsed_s": round(job.elapsed_s(), 1),
        },
    )


def _record_history(job: JobState, req: GenerateRequest, game_id: str) -> None:
    try:
        # Make sure the session the frontend submitted is registered. If the
        # user's localStorage carries an id from a backend instance that no
        # longer exists, an unregistered id would silently orphan the game.
        sessions.ensure_registered(req.session_id)
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


def _remember_cwd(job: JobState, cwd: str) -> None:
    job.subprocess_cwd = cwd


async def _run_job(job: JobState, req: GenerateRequest) -> None:
    job.mark_running()
    logger.info(f"job {job.job_id}: running (recipe={req.visual_recipe})")
    try:
        result = await generate(
            concept=req.concept.model_dump(),
            style_triplet_summary=_style_summary(req),
            visual_recipe_name=req.visual_recipe,
            on_start=lambda cwd: _remember_cwd(job, cwd),
            publish=job.publish,
        )
    except asyncio.CancelledError:
        job.mark_cancelled()
        job.publish(_terminal_event(job))
        logger.info(f"job {job.job_id}: cancelled ({job.elapsed_s():.0f}s)")
        raise
    except RateLimitedError as exc:
        job.mark_failed(f"rate_limited: {exc}")
        job.publish(_terminal_event(job))
        _reap_post_failure(job, "rate-limited")
        logger.warning(f"job {job.job_id}: rate-limited (resets_at={exc.resets_at})")
    except GenerationStalledError as exc:
        job.mark_failed(f"stalled: {exc}")
        job.publish(_terminal_event(job))
        _reap_post_failure(job, "stalled")
        logger.warning(f"job {job.job_id}: stalled - {exc!r}")
    except Exception as exc:
        job.mark_failed(str(exc))
        job.publish(_terminal_event(job))
        _reap_post_failure(job, "errored")
        logger.warning(f"job {job.job_id}: failed ({job.elapsed_s():.0f}s) - {exc!r}")
    else:
        job.mark_done(game_id=result["game_id"], summary=result["summary"])
        _record_history(job, req, result["game_id"])
        job.publish(_terminal_event(job))
        logger.info(f"job {job.job_id}: done game_id={result['game_id']} ({job.elapsed_s():.0f}s)")


def _reap_post_failure(job: JobState, reason: str) -> None:
    """After a non-cancel failure (stall / rate-limit / unexpected exception),
    walk our child tree and SIGKILL any SDK subprocess that didn't self-clean.

    Why this is needed: the SDK's ``close()`` chain only runs when the
    user-facing async generator is fully exhausted or explicitly closed.
    On a watchdog timeout or rate-limit raise we DO close the generator
    via ``contextlib.suppress`` in ``_drain`` — but the SDK's close()
    itself awaits ``self._process.wait()``, which can hang forever if the
    subprocess is blocked on a dead TCP socket (the exact failure mode
    that triggered the watchdog in the first place)."""
    killed = _kill_orphaned_sdk_subprocesses(job.subprocess_cwd)
    if killed:
        logger.warning(
            f"job {job.job_id}: post-{reason}, hard-killed {killed} orphan subprocess(es)"
        )


def _kill_orphaned_sdk_subprocesses(cwd: str | None) -> int:
    """SIGKILL any child process still living inside the job's game dir.

    The SDK's asyncio cleanup chain (``process_query.finally → query.close →
    process.wait``) re-raises ``CancelledError`` on each await when its task
    is being cancelled, so SIGTERM never reaches the ``claude`` subprocess.
    Walking our own child tree by cwd is the only reliable way to evict it.
    """
    if not cwd:
        return 0
    killed = 0
    try:
        children = psutil.Process().children(recursive=True)
    except psutil.Error:
        return 0
    cwd_prefix = cwd.rstrip("/") + "/"
    for child in children:
        try:
            child_cwd = child.cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if child_cwd == cwd or child_cwd.startswith(cwd_prefix):
            try:
                child.kill()
                killed += 1
                logger.warning(
                    f"hard-killed orphan SDK subprocess pid={child.pid} cwd={child_cwd}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return killed


async def _settle(task: asyncio.Task[None]) -> None:
    """Await a task swallowing any exception so wait_for sees normal completion."""
    with contextlib.suppress(BaseException):
        await task


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(req: GenerateRequest) -> GenerateAccepted:
    """Fire-and-forget. Client polls GET /api/game/job/{job_id} for state,
    or opens GET /api/game/job/{job_id}/stream for live progress events."""
    job = jobs.new_job()
    task = asyncio.create_task(_run_job(job, req))
    job.task = task
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return GenerateAccepted(
        job_id=job.job_id,
        status=job.status,
        status_url=f"/api/game/job/{job.job_id}",
        stream_url=f"/api/game/job/{job.job_id}/stream",
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str) -> JobView:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job {job_id}")
    return _job_view(job)


@router.delete("/job/{job_id}")
async def cancel_job(job_id: str) -> JobView:
    """Stop an in-flight generation.

    Idempotent: already-finished jobs return their current state unchanged.

    Cancellation flow:
    1. ``task.cancel()`` — best effort; the SDK's own cleanup chain may
       fail to send SIGTERM because its awaits are re-interrupted.
    2. Wait up to ``_CANCEL_GRACE_S`` for the task to settle.
    3. Walk our child tree and SIGKILL any subprocess still inside the
       job's cwd — this is the only reliable way to evict a zombie.
    4. Mark the job ``cancelled`` and publish a terminal event so the
       SSE stream closes cleanly.
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job {job_id}")
    if job.status in _TERMINAL_STATUSES:
        return _job_view(job)

    if job.task is not None and not job.task.done():
        job.task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(_settle(job.task)), timeout=_CANCEL_GRACE_S)
        except (TimeoutError, asyncio.CancelledError):
            logger.info(f"job {job_id}: graceful cancel timed out — escalating to SIGKILL")

    killed = _kill_orphaned_sdk_subprocesses(job.subprocess_cwd)
    if killed:
        logger.info(f"job {job_id}: hard-killed {killed} orphan SDK subprocess(es)")

    if job.status not in _TERMINAL_STATUSES:
        job.mark_cancelled()
        job.publish(_terminal_event(job))

    logger.info(f"job {job_id}: cancel finalised (status={job.status})")
    return _job_view(job)


@router.get("/job/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    """Server-Sent Events feed of job progress.

    Each frame is ``event: <type>\\ndata: <json>\\n\\n``. The stream closes
    after a terminal event (``done`` / ``failed`` / ``cancelled``). A
    heartbeat fires every 5 s when no other event is pending so the
    browser's EventSource stays open.

    Designed for a single in-flight consumer per job (the demo's single-tab
    usage); a second simultaneous consumer would steal events from the first.
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job {job_id}")

    return StreamingResponse(_event_source(job), media_type="text/event-stream")


async def _event_source(job: JobState) -> AsyncIterator[bytes]:
    # Replay current status so a late-joining EventSource doesn't sit blank.
    yield _sse(
        JobEvent(
            type="hello",
            ts=time.time(),
            data={
                "status": job.status,
                "elapsed_s": round(job.elapsed_s(), 1),
                "game_id": job.game_id,
            },
        )
    )

    if job.status in _TERMINAL_STATUSES:
        yield _sse(_terminal_event(job))
        return

    while True:
        try:
            event = await asyncio.wait_for(job.events.get(), timeout=5.0)
        except TimeoutError:
            yield _sse(
                JobEvent(
                    type="heartbeat",
                    ts=time.time(),
                    data={"elapsed_s": round(job.elapsed_s(), 1)},
                )
            )
            if job.status in _TERMINAL_STATUSES:
                # Task finished without us seeing the terminal event (queue
                # drained between get() calls); synthesise it from job state.
                yield _sse(_terminal_event(job))
                return
            continue

        yield _sse(event)
        if event.type in _TERMINAL_STATUSES:
            return


def _sse(event: JobEvent) -> bytes:
    payload = event.model_dump_json()
    return f"event: {event.type}\ndata: {payload}\n\n".encode()


@router.get("/{game_id}/play")
async def play_game(game_id: str) -> FileResponse:
    # Restrict to alphanumeric/hyphen to avoid path traversal.
    if not game_id.replace("-", "").isalnum():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid game id")
    path = GENERATED_GAMES_DIR / game_id / "game.html"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"game {game_id} not found")
    return FileResponse(path, media_type="text/html")


@router.get("/showcase/all")
async def showcase_all() -> dict[str, list[dict[str, object]]]:
    """Unified works catalogue powering the frontend's WorksGrid + /works page.

    Source of truth is the per-session history index (``data/history/*.json``)
    because those entries carry the full metadata a card needs: title +
    tagline + art × mechanic × mood × visual_recipe + audio_hash. We then
    scan ``generated-games/*/game.html`` and append any orphan that has no
    history entry (early demos, manual smoke tests) with a summary fallback
    parsed from SUMMARY.md.

    Each entry returns:
      - game_id
      - title, tagline, art, mechanic, mood, visual_recipe (None for orphans)
      - audio_url: relative URL if the original .wav still exists, else None
      - play_url
      - created_at (unix seconds, history time when available, otherwise
                    file mtime — sorted newest-first by this)
      - has_history (whether the entry came from the index or filesystem)
    """
    import json

    from bark_to_game import paths

    items_by_id: dict[str, dict[str, object]] = {}

    # Pass 1: history index. Every session file is a list of HistoryEntry dicts.
    if paths.HISTORY_DIR.exists():
        for history_file in paths.HISTORY_DIR.glob("*.json"):
            try:
                entries = json.loads(history_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for entry in entries:
                game_id = entry.get("game_id")
                if not game_id:
                    continue
                audio_hash = entry.get("audio_hash") or None
                audio_url = None
                if audio_hash and (paths.AUDIO_DIR / f"{audio_hash}.wav").exists():
                    audio_url = f"/api/audio/{audio_hash}/play"
                items_by_id[game_id] = {
                    "game_id": game_id,
                    "title": entry.get("title") or "",
                    "tagline": entry.get("tagline") or "",
                    "art": entry.get("art") or "",
                    "mechanic": entry.get("mechanic") or "",
                    "mood": entry.get("mood") or "",
                    "visual_recipe": entry.get("visual_recipe") or "",
                    "audio_url": audio_url,
                    "play_url": f"/api/game/{game_id}/play",
                    "created_at": float(entry.get("created_at") or 0.0),
                    "has_history": True,
                }

    # Pass 2: filesystem orphans — games that exist on disk but never made it
    # into the history index. Use SUMMARY.md as a best-effort title source.
    if GENERATED_GAMES_DIR.exists():
        for child in GENERATED_GAMES_DIR.iterdir():
            if not child.is_dir() or child.name in items_by_id:
                continue
            game_path = child / "game.html"
            if not game_path.exists():
                continue
            summary_path = child / "SUMMARY.md"
            summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
            # Pull a title out of the SUMMARY.md. Accept both the plain
            # ``TITLE — blurb`` shape and the bold ``**TITLE** — blurb``
            # shape; markdown ``# Title`` headers are also tolerated.
            title = ""
            tagline = ""
            if summary:
                first_line = summary.split("\n", 1)[0].strip().lstrip("#").strip()
                separator = "—" if "—" in first_line else ("-" if "-" in first_line else None)
                if separator:
                    head, tail = first_line.split(separator, 1)
                    title = head.strip().strip("*").strip()
                    tagline = tail.strip().strip("*").strip()
                else:
                    title = first_line.strip("*").strip()
            items_by_id[child.name] = {
                "game_id": child.name,
                "title": title or f"作品 {child.name[:8]}",
                "tagline": tagline,
                "art": "",
                "mechanic": "",
                "mood": "",
                "visual_recipe": "",
                "audio_url": None,
                "play_url": f"/api/game/{child.name}/play",
                "created_at": game_path.stat().st_mtime,
                "has_history": False,
            }

    # Skip any history entry whose game.html no longer exists on disk
    # (e.g. cancelled jobs that still left a row). The frontend's
    # ▶ button would 404 on those, which is worse than hiding them.
    items = [
        it for it in items_by_id.values()
        if (GENERATED_GAMES_DIR / str(it["game_id"]) / "game.html").exists()
    ]
    items.sort(key=lambda it: it["created_at"], reverse=True)
    return {"items": items}
