"""Session metadata persistence.

Sessions are an application-level concept layered on top of the existing
session_id used by the MAP-Elites archive (data/archive/{id}.json). The
manager keeps a small index file so the UI can name, list, and switch
sessions; the underlying per-session data (archive, generated games) is
keyed by the same id regardless.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import TypedDict, cast

from bark_to_game.paths import DATA_DIR

SESSIONS_DIR = DATA_DIR / "sessions"
INDEX_PATH = SESSIONS_DIR / "index.json"
DEFAULT_ID = "default"
DEFAULT_NAME = "default"


class SessionMeta(TypedDict):
    id: str
    name: str
    created_at: float


def _read_index() -> list[SessionMeta]:
    if not INDEX_PATH.exists():
        return []
    return cast(list[SessionMeta], json.loads(INDEX_PATH.read_text()))


def _write_index(sessions: list[SessionMeta]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(sessions, indent=2))


def _ensure_default(sessions: list[SessionMeta]) -> list[SessionMeta]:
    if any(s["id"] == DEFAULT_ID for s in sessions):
        return sessions
    sessions.insert(
        0,
        SessionMeta(id=DEFAULT_ID, name=DEFAULT_NAME, created_at=time.time()),
    )
    _write_index(sessions)
    return sessions


def list_all() -> list[SessionMeta]:
    return _ensure_default(_read_index())


def get(session_id: str) -> SessionMeta | None:
    for s in list_all():
        if s["id"] == session_id:
            return s
    return None


def create(name: str | None = None) -> SessionMeta:
    sessions = list_all()
    sid = secrets.token_hex(4)
    clean = (name or "").strip()
    if not clean:
        clean = f"session #{len(sessions) + 1}"
    meta = SessionMeta(id=sid, name=clean, created_at=time.time())
    sessions.append(meta)
    _write_index(sessions)
    return meta
