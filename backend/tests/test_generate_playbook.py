"""Playbook is loadable and contains the expected sections."""

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
