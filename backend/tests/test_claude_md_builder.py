"""CLAUDE.md spec assembly — rubric + audio DNA sections.

These tests pin the contract between translate (which produces concept
rubric fields + game_params) and generate (which consumes them in the
single spec it writes for Claude). If a section quietly drops out, the
generator silently loses the playability guidance that drove the rubric
in the first place.
"""

from __future__ import annotations

from typing import Any

from bark_to_game.generate import _common


_CONCEPT_WITH_RUBRIC: dict[str, Any] = {
    "title": "Bark Quest",
    "tagline": "A barky journey",
    "player": "you, the kitchen dog",
    "core_mechanic": "catch falling treats",
    "win_condition": "catch 12 in a row",
    "fail_condition": "drop 3",
    "onboarding_hint": "first treat pulses with a yellow ring at the centre",
    "escalation_moment": "WAVE 2 banner when 6 treats are caught",
    "replay_hook": "personal-best treat count",
    "visual_summary": "warm kitchen",
    "audio_summary": "kalimba plink",
}

_GAME_PARAMS: dict[str, Any] = {
    "tempo": "fast",
    "density": "moderate",
    "intensity": "firm",
    "variability": "shifting",
    "spawn_interval_ms": 600,
    "max_concurrent": 8,
    "escalation_per_min": 1.55,
    "randomness_pct": 30,
}

_STYLE = "- Art: **claymation** - x\n- Mechanic: **catch** - y\n- Mood: **mischievous** - z"


def test_rubric_section_is_emitted_when_fields_present() -> None:
    md = _common.build_claude_md(_CONCEPT_WITH_RUBRIC, _STYLE, "pixel_crt", _GAME_PARAMS)
    assert "## PLAYABILITY REQUIREMENTS" in md
    assert "first treat pulses with a yellow ring" in md
    assert "WAVE 2 banner when 6 treats are caught" in md
    assert "personal-best treat count" in md


def test_rubric_section_degrades_gracefully_when_fields_empty() -> None:
    """Missing rubric fields → section still renders but with the default note."""
    concept = {**_CONCEPT_WITH_RUBRIC, "onboarding_hint": "", "escalation_moment": "", "replay_hook": ""}
    md = _common.build_claude_md(concept, _STYLE, "pixel_crt", _GAME_PARAMS)
    assert "## PLAYABILITY REQUIREMENTS" in md
    assert "(none provided" in md  # the explicit graceful-degrade line


def test_audio_dna_block_renders_concrete_integers() -> None:
    md = _common.build_claude_md(_CONCEPT_WITH_RUBRIC, _STYLE, "pixel_crt", _GAME_PARAMS)
    assert "## AUDIO DNA" in md
    # Concrete numbers must land in the spec verbatim for the generator to copy.
    assert "600 ms" in md or "600`" in md  # spawn_interval_ms
    assert "8" in md   # max_concurrent
    assert "1.55" in md
    assert "30%" in md or "±30" in md


def test_audio_dna_falls_back_when_params_missing() -> None:
    md = _common.build_claude_md(_CONCEPT_WITH_RUBRIC, _STYLE, "pixel_crt", None)
    assert "## AUDIO DNA" in md
    assert "no audio DNA" in md  # explicit fallback line


def test_spec_includes_recipe_and_playbook() -> None:
    md = _common.build_claude_md(_CONCEPT_WITH_RUBRIC, _STYLE, "pixel_crt", _GAME_PARAMS)
    # Recipe contents land verbatim:
    assert "Recipe: pixel_crt" in md
    # Playbook gets loaded:
    assert "Game Playbook" in md
