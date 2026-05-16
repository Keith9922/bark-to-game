"""Per-session history of completed games.

Append-only JSON files at data/history/{session_id}.json. Each entry is enough
for the UI to render a row (title + tagline + style triplet + recipe + audio
hash) plus the game_id and audio_hash so the iframe + audio player can fetch
the corresponding artifacts.

Audio file existence is checked at fetch time — the file may or may not be on
disk (older games predate the audio-persistence feature).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from bark_to_game.paths import AUDIO_DIR, HISTORY_DIR

MAX_HISTORY_PER_SESSION = 50


@dataclass(frozen=True)
class HistoryEntry:
    game_id: str
    session_id: str
    created_at: float
    title: str
    tagline: str
    audio_hash: str
    visual_recipe: str
    art: str
    mechanic: str
    mood: str


def _path(session_id: str) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR / f"{session_id}.json"


def _load_raw(session_id: str) -> list[dict[str, Any]]:
    p = _path(session_id)
    if not p.exists():
        return []
    return cast(list[dict[str, Any]], json.loads(p.read_text()))


def list_for_session(session_id: str = "default") -> list[HistoryEntry]:
    """Newest-first list of past games for the given session."""
    rows = _load_raw(session_id)
    rows.sort(key=lambda r: r.get("created_at", 0.0), reverse=True)
    return [HistoryEntry(**row) for row in rows]


def record(entry: HistoryEntry) -> None:
    rows = _load_raw(entry.session_id)
    rows.append(asdict(entry))
    # newest-first cap, keep the most recent N
    rows.sort(key=lambda r: r.get("created_at", 0.0), reverse=True)
    rows = rows[:MAX_HISTORY_PER_SESSION]
    _path(entry.session_id).write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def audio_path_for(audio_hash: str) -> Path:
    """Resolve disk path for an audio hash. Existence not guaranteed."""
    return AUDIO_DIR / f"{audio_hash}.wav"


def has_audio(audio_hash: str) -> bool:
    return bool(audio_path_for(audio_hash).exists())
