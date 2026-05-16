"""In-memory async job registry for long-running game generation.

Why in-memory: single-user localhost demo. State dies on restart, but the
underlying game.html artifacts persist in generated-games/ so a refresh of
the browser can still load them via /api/game/{game_id}/play.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Literal

JobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "pending"
    game_id: str | None = None
    summary: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

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

    def elapsed_s(self) -> float:
        return (self.finished_at or time.time()) - self.created_at


_REGISTRY: dict[str, JobState] = {}


def new_job() -> JobState:
    job = JobState(job_id=secrets.token_hex(6))
    _REGISTRY[job.job_id] = job
    return job


def get(job_id: str) -> JobState | None:
    return _REGISTRY.get(job_id)


def reset_for_tests() -> None:
    _REGISTRY.clear()
