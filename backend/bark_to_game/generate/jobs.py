"""In-memory async job registry for long-running game generation.

Why in-memory: single-user localhost demo. State dies on restart, but the
underlying game.html artifacts persist in generated-games/ so a refresh of
the browser can still load them via /api/game/{game_id}/play.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Literal

from bark_to_game.schemas.game import JobEvent

JobStatus = Literal["pending", "running", "done", "failed", "cancelled"]


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "pending"
    game_id: str | None = None
    summary: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    # Reference to the background task so callers can cancel it.
    task: asyncio.Task[None] | None = field(default=None, repr=False)
    # cwd of the SDK subprocess, captured early so cancel can hard-kill it
    # if the SDK's own asyncio cleanup chain gets re-cancelled mid-await.
    subprocess_cwd: str | None = field(default=None, repr=False)
    # Live event stream consumed by GET /job/{id}/stream. Bounded so a stalled
    # consumer cannot wedge generation; we drop oldest on overflow.
    events: asyncio.Queue[JobEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=200), repr=False
    )

    def mark_running(self) -> None:
        self.status = "running"

    def mark_done(self, game_id: str, summary: str) -> None:
        self.game_id = game_id
        self.summary = summary
        self.status = "done"
        self.finished_at = time.time()

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.status = "failed"
        self.finished_at = time.time()

    def mark_cancelled(self) -> None:
        self.status = "cancelled"
        self.finished_at = time.time()

    def elapsed_s(self) -> float:
        return (self.finished_at or time.time()) - self.created_at

    def publish(self, event: JobEvent) -> None:
        """Non-blocking publish; drop oldest if the SSE consumer is too slow."""
        if self.events.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.events.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self.events.put_nowait(event)


_REGISTRY: dict[str, JobState] = {}


def new_job() -> JobState:
    job = JobState(job_id=secrets.token_hex(6))
    _REGISTRY[job.job_id] = job
    return job


def get(job_id: str) -> JobState | None:
    return _REGISTRY.get(job_id)


def reset_for_tests() -> None:
    _REGISTRY.clear()
