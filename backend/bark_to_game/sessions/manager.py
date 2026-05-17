"""Session metadata persistence.

Sessions are an application-level concept layered on top of the existing
session_id used by the MAP-Elites archive (data/archive/{id}.json). The
manager keeps a small index file so the UI can name, list, and switch
sessions; the underlying per-session data (archive, generated games) is
keyed by the same id regardless.

Orphan handling: a session_id can show up in ``data/history/*.json`` without
ever being in ``index.json`` — most commonly when the frontend's
localStorage holds an id from an older backend that no longer exists. We
treat those as recoverable: ``list_all()`` discovers them on disk and
adopts them with a friendly name, so the user sees their game in the
dropdown instead of it being orphaned.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import TypedDict, cast

from bark_to_game import paths

# Module-level helpers that re-read paths.* each call so tests (and any
# future runtime DATA_DIR reconfig) take effect without monkeypatching
# every module that imports these constants.


def _sessions_dir() -> Path:
    return paths.DATA_DIR / "sessions"


def _index_path() -> Path:
    return _sessions_dir() / "index.json"


# Back-compat for callers that imported these names directly. The functions
# above are the source of truth at call time; these are snapshot views.
SESSIONS_DIR = paths.DATA_DIR / "sessions"
INDEX_PATH = SESSIONS_DIR / "index.json"
DEFAULT_ID = "default"
DEFAULT_NAME = "default"

# Session ids the manager creates are 8 lowercase hex chars (token_hex(4)).
# We accept the same shape from frontend localStorage during orphan recovery,
# plus the special "default" id. Anything else (e.g. test fixtures like
# "route-test") is ignored so test pollution doesn't end up in the UI.
_VALID_ID_RE = re.compile(r"^[0-9a-f]{8}$")


class SessionMeta(TypedDict):
    id: str
    name: str
    created_at: float


def _read_index() -> list[SessionMeta]:
    if not _index_path().exists():
        return []
    return cast(list[SessionMeta], json.loads(_index_path().read_text()))


def _write_index(sessions: list[SessionMeta]) -> None:
    _sessions_dir().mkdir(parents=True, exist_ok=True)
    _index_path().write_text(json.dumps(sessions, indent=2))


def _is_valid_session_id(session_id: str) -> bool:
    return session_id == DEFAULT_ID or bool(_VALID_ID_RE.match(session_id))


def _adopt_orphans(sessions: list[SessionMeta]) -> list[SessionMeta]:
    """Scan history dir for session_ids missing from index.json and adopt them.

    Skips test-fixture ids like ``route-test`` so we don't pollute the UI.
    The adopted session gets a placeholder name ("话题 abc12345"); the user
    can rename via a future endpoint if we add one.
    """
    history_dir = paths.HISTORY_DIR
    if not history_dir.exists():
        return sessions
    known = {s["id"] for s in sessions}
    appended = False
    for path in sorted(history_dir.glob("*.json")):
        sid = path.stem
        if sid in known or not _is_valid_session_id(sid):
            continue
        sessions.append(
            SessionMeta(
                id=sid,
                name=f"话题 {sid}",
                created_at=path.stat().st_mtime,
            )
        )
        known.add(sid)
        appended = True
    if appended:
        _write_index(sessions)
    return sessions


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
    return _adopt_orphans(_ensure_default(_read_index()))


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


def ensure_registered(session_id: str) -> SessionMeta:
    """Adopt ``session_id`` into the index if it isn't already known.

    Called from generate / translate so a frontend that submits an id from
    stale localStorage doesn't silently drop into a session the dropdown
    can't show. Returns the existing or newly-created SessionMeta.
    """
    existing = get(session_id)
    if existing is not None:
        return existing
    if not _is_valid_session_id(session_id):
        # Non-conforming id (test fixture, garbage from a malicious client) —
        # do not pollute the registry. Caller still gets its data written
        # under that id, but the UI won't surface it.
        return SessionMeta(id=session_id, name=session_id, created_at=time.time())
    sessions = list_all()
    meta = SessionMeta(
        id=session_id,
        name=f"话题 {session_id}",
        created_at=time.time(),
    )
    sessions.append(meta)
    _write_index(sessions)
    return meta
