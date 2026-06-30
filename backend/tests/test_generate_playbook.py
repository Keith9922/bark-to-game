"""Playbook is loadable, sliceable, and contains the expected sections."""

from __future__ import annotations

from bark_to_game.generate import playbook


def test_playbook_loads() -> None:
    text = playbook.load()
    assert len(text) > 500


def test_playbook_has_core_sections() -> None:
    text = playbook.load()
    for section in (
        "Single-file scaffold",
        "Input",
        "Web Audio",
        "Canvas helpers",
        "Common mechanics",
        "Game-over loop",
    ):
        assert section in text, f"playbook missing section: {section!r}"


def test_load_for_returns_only_matching_sketch() -> None:
    """Sliced load must contain the wanted sketch + universal sections,
    and NOT contain other mechanics' sketches (the whole point of slicing)."""
    snake_md = playbook.load_for("snake")
    # Shared core present:
    assert "Single-file scaffold" in snake_md
    assert "Always-visible HUD" in snake_md
    assert "Audio DNA usage" in snake_md
    assert "Game-over loop" in snake_md
    # Wanted sketch present:
    assert "### Snake" in snake_md
    # Unrelated sketches absent:
    assert "### Sokoban" not in snake_md
    assert "### Catch" not in snake_md
    assert "### Roguelike_dive" not in snake_md


def test_load_for_handles_name_normalisation() -> None:
    """JSON 'charge_release' must match playbook heading 'Charge-release'."""
    md = playbook.load_for("charge_release")
    assert "### Charge-release" in md


def test_load_for_unknown_mechanic_returns_core_only() -> None:
    """Unknown mechanic: still ship the universal shared core, no sketches."""
    md = playbook.load_for("some_completely_unknown_mechanic")
    assert "Single-file scaffold" in md          # shared core
    assert "Game-over loop" in md                 # epilogue
    assert "Sketch for THIS" not in md           # no per-mechanic block


def test_load_for_smaller_than_full_for_known_mechanics() -> None:
    """The whole point of slicing: a single-mechanic load is smaller than the
    full playbook. This keeps generate input stable as the pool grows."""
    full_len = len(playbook.load())
    for m in ("catch", "snake", "roguelike_dive"):
        sliced_len = len(playbook.load_for(m))
        assert sliced_len < full_len, (
            f"slice for {m} ({sliced_len}) not smaller than full ({full_len})"
        )


def test_classic_mechanics_have_sketches() -> None:
    """The six newly-added classic mechanics each ship with a code sketch."""
    for mech in ("link_pair", "snake", "sokoban", "runner", "jumper", "roguelike_dive"):
        md = playbook.load_for(mech)
        assert "Sketch for THIS" in md, f"{mech} missing per-mechanic sketch"
