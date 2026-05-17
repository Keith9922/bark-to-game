"""Tests for orphan-session recovery in sessions.manager.

Regression for the user-visible bug where a game generation completed but
the entry never showed up in the history panel: the session_id was in the
frontend's localStorage but not registered server-side, so the dropdown
couldn't surface it.
"""

from __future__ import annotations

import json
from pathlib import Path

from bark_to_game import paths
from bark_to_game.sessions import manager


def _write_orphan_history(session_id: str) -> None:
    (paths.HISTORY_DIR / f"{session_id}.json").write_text("[]")


def test_list_all_adopts_orphan_history_file() -> None:
    _write_orphan_history("abcd1234")

    sessions = manager.list_all()
    ids = [s["id"] for s in sessions]
    assert "abcd1234" in ids, "orphan session_id from history dir should be adopted"
    adopted = next(s for s in sessions if s["id"] == "abcd1234")
    assert adopted["name"].startswith("话题 ") or adopted["name"].startswith("话题 ")
    assert adopted["name"].endswith("abcd1234")


def test_list_all_skips_non_hex_orphan_ids() -> None:
    """Test-fixture filenames like ``route-test.json`` would otherwise
    pollute the dropdown. The id-shape filter keeps them out."""
    _write_orphan_history("route-test")
    _write_orphan_history("stream-test")
    _write_orphan_history("warmup")

    ids = [s["id"] for s in manager.list_all()]
    for noise in ("route-test", "stream-test", "warmup"):
        assert noise not in ids


def test_list_all_persists_adopted_orphans_to_index() -> None:
    _write_orphan_history("deadbeef")

    manager.list_all()  # adopt
    raw = json.loads(manager.INDEX_PATH.read_text())
    ids = [s["id"] for s in raw]
    assert "deadbeef" in ids, "adoption should write to index.json on first call"

    # Second call must NOT duplicate the entry.
    manager.list_all()
    raw_again = json.loads(manager.INDEX_PATH.read_text())
    deadbeef = [s for s in raw_again if s["id"] == "deadbeef"]
    assert len(deadbeef) == 1


def test_ensure_registered_adopts_unknown_valid_id() -> None:
    meta = manager.ensure_registered("12345678")
    assert meta["id"] == "12345678"
    ids = [s["id"] for s in manager.list_all()]
    assert ids.count("12345678") == 1, "must register exactly once"


def test_ensure_registered_returns_existing_for_known_id() -> None:
    created = manager.create(name="my session")
    meta = manager.ensure_registered(created["id"])
    assert meta == created


def test_ensure_registered_skips_index_for_invalid_shape() -> None:
    """A non-hex id (e.g. a test fixture or garbage) must not pollute the
    dropdown, but the caller still receives a usable meta object so its
    history write doesn't fail."""
    meta = manager.ensure_registered("route-test")
    assert meta["id"] == "route-test"  # caller can still use it
    ids = [s["id"] for s in manager.list_all()]
    assert "route-test" not in ids  # but not in the user-visible list


def test_default_session_is_present_and_only_once_after_orphan_adoption() -> None:
    _write_orphan_history("ff27af63")
    sessions = manager.list_all()
    defaults = [s for s in sessions if s["id"] == manager.DEFAULT_ID]
    assert len(defaults) == 1, "default must remain singular even after adoptions"


def test_orphan_created_at_uses_history_mtime(tmp_path: Path) -> None:
    """The adopted session's ``created_at`` should reflect when the user
    actually had data in that session, not 'now' — otherwise newest-first
    ordering puts adopted sessions ahead of legitimate older ones."""
    import os
    import time

    target = paths.HISTORY_DIR / "abcdef01.json"
    target.write_text("[]")
    five_min_ago = time.time() - 300
    os.utime(target, (five_min_ago, five_min_ago))

    meta = next(s for s in manager.list_all() if s["id"] == "abcdef01")
    assert abs(meta["created_at"] - five_min_ago) < 1.0
