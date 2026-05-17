"""MAP-Elites archive read/write/cap behaviour."""

from __future__ import annotations

import pytest

from bark_to_game.translate import archive


@pytest.fixture
def tmp_archive(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)


def test_load_returns_empty_for_unknown_session(tmp_archive: None) -> None:
    assert archive.load("brand-new-session") == []


def test_record_then_load_roundtrip(tmp_archive: None) -> None:
    archive.record("s1", ("cubism", "catch", "serene"), "Game A — a tagline", "abc")
    archive.record("s1", ("ukiyo-e", "rhythm", "majestic"), "Game B — another", "def")
    entries = archive.load("s1")
    assert len(entries) == 2
    assert entries[0].summary == "Game A — a tagline"
    assert entries[1].cell == ("ukiyo-e", "rhythm", "majestic")


def test_recent_summaries_returns_tail(tmp_archive: None) -> None:
    for i in range(10):
        archive.record("s1", ("a", "b", "c"), f"Game #{i} — t", f"hash{i}")
    recent = archive.recent_summaries("s1", n=3)
    assert recent == ["Game #7 — t", "Game #8 — t", "Game #9 — t"]


def test_occupied_cells(tmp_archive: None) -> None:
    archive.record("s1", ("cubism", "catch", "serene"), "x — y", "h1")
    archive.record("s1", ("cubism", "catch", "serene"), "z — w", "h2")
    archive.record("s1", ("bauhaus", "dodge", "chaotic"), "a — b", "h3")
    cells = archive.occupied_cells("s1")
    assert cells == {("cubism", "catch", "serene"), ("bauhaus", "dodge", "chaotic")}


def test_history_is_capped(tmp_archive: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "MAX_HISTORY_PER_SESSION", 5)
    for i in range(20):
        archive.record("s1", ("a", "b", "c"), f"t{i}", f"h{i}")
    entries = archive.load("s1")
    assert len(entries) == 5
    # Latest 5 retained (oldest dropped)
    assert entries[0].audio_hash == "h15"
    assert entries[-1].audio_hash == "h19"
