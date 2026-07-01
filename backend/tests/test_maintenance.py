"""Tests for the husk-sweep maintenance utility."""

from __future__ import annotations

from pathlib import Path

from bark_to_game.generate.maintenance import sweep_husks


def test_sweep_removes_husks_keeps_games(tmp_path: Path) -> None:
    # Use a subdir, not tmp_path itself: the autouse _isolate_data_dirs fixture
    # creates tmp_path/data, which would otherwise be swept as a husk.
    games = tmp_path / "games"
    games.mkdir()

    good = games / "good"
    good.mkdir()
    (good / "game.html").write_text("<html></html>")
    (good / "CLAUDE.md").write_text("spec")

    husk1 = games / "husk1"
    husk1.mkdir()
    (husk1 / "CLAUDE.md").write_text("spec")  # no game.html
    husk2 = games / "husk2"
    husk2.mkdir()  # empty

    (games / "loose.txt").write_text("not a dir entry we touch")

    removed = sweep_husks(games, dry_run=False)

    assert set(removed) == {"husk1", "husk2"}
    assert good.exists() and (good / "game.html").exists()
    assert not husk1.exists()
    assert not husk2.exists()


def test_sweep_dry_run_reports_but_keeps(tmp_path: Path) -> None:
    games = tmp_path / "games"
    games.mkdir()
    husk = games / "husk"
    husk.mkdir()
    (husk / "CLAUDE.md").write_text("spec")

    removed = sweep_husks(games, dry_run=True)

    assert removed == ["husk"]
    assert husk.exists()  # dry-run did not delete
