"""Per-session MAP-Elites archive of past generated concepts.

A concept is reduced to a behaviour key `(art, mechanic, mood)` and stored
along with a short summary. The translate engine consults the archive to (a)
list recent summaries for an "AVOID these" prompt section and (b) penalise
candidates whose `(art, mechanic, mood)` cell is already occupied.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from bark_to_game.paths import ARCHIVE_DIR

MAX_HISTORY_PER_SESSION = 50


@dataclass(frozen=True)
class Entry:
    timestamp: float
    cell: tuple[str, str, str]  # (art, mechanic, mood)
    summary: str
    audio_hash: str


def _path(session_id: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    return ARCHIVE_DIR / f"{session_id}.json"


def _load_raw(session_id: str) -> list[dict[str, Any]]:
    p = _path(session_id)
    if not p.exists():
        return []
    return cast(list[dict[str, Any]], json.loads(p.read_text()))


def load(session_id: str = "default") -> list[Entry]:
    return [
        Entry(
            timestamp=row["timestamp"],
            cell=cast(tuple[str, str, str], tuple(row["cell"])),
            summary=row["summary"],
            audio_hash=row["audio_hash"],
        )
        for row in _load_raw(session_id)
    ]


def record(
    session_id: str,
    cell: tuple[str, str, str],
    summary: str,
    audio_hash: str,
) -> None:
    rows = _load_raw(session_id)
    rows.append(
        {
            "timestamp": time.time(),
            "cell": list(cell),
            "summary": summary,
            "audio_hash": audio_hash,
        }
    )
    rows = rows[-MAX_HISTORY_PER_SESSION:]
    _path(session_id).write_text(json.dumps(rows, indent=2))


def recent_summaries(session_id: str = "default", n: int = 5) -> list[str]:
    return [e.summary for e in load(session_id)[-n:]]


def occupied_cells(session_id: str = "default") -> set[tuple[str, str, str]]:
    return {e.cell for e in load(session_id)}
