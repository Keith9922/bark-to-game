"""Translate user-prompt assembly — playability rubric + audio DNA blocks.

We assert the structure of the prompt so a future tweak to the LLM-facing
copy doesn't silently drop the rubric or AUDIO DNA section that the model
relies on to honour the constraints.
"""

from __future__ import annotations

from typing import Any

from bark_to_game.translate import prompts


_TOKENS: list[dict[str, Any]] = [
    {
        "type": "BARK", "pitch": "MID", "duration": "SHORT",
        "intensity": "LOUD", "contour": "FLAT",
    }
]
_SUMMARY = {"rhythm": "STACCATO", "mood": "AGITATED", "entropy": 0.7}
_GAME_PARAMS = {
    "tempo": "frantic",
    "density": "dense",
    "intensity": "harsh",
    "variability": "wild",
    "spawn_interval_ms": 350,
    "max_concurrent": 14,
    "escalation_per_min": 1.8,
    "randomness_pct": 60,
}
_STYLE: dict[str, Any] = {
    "art": {"name": "papercut", "description": "x", "palette_hint": "p"},
    "mechanic": {
        "name": "deflect",
        "description": "y",
        "input": "aim",
        "core_loop": "Aim deflection; chain ricochets; missed objects drain shield.",
    },
    "mood": {"name": "anxious", "description": "z"},
}
_RECIPE = {"name": "pixel_crt", "markdown": "# Recipe pixel_crt\n..."}


def test_system_prompt_carries_rubric_and_audio_dna_sections() -> None:
    sp = prompts.SYSTEM_PROMPT
    assert "PLAYABILITY RUBRIC" in sp
    assert "AUDIO DNA BINDING" in sp
    # Six rubric items by ordinal — the model will see and answer them.
    for item in ("CORE ACTION", "VISIBLE GOAL", "VISIBLE THREAT", "ZERO-READ ONBOARDING", "ESCALATION MOMENT", "REPLAY HOOK"):
        assert item in sp, f"missing rubric item: {item}"
    # New schema fields are required in the JSON spec the model emits.
    for field in ("onboarding_hint", "escalation_moment", "replay_hook"):
        assert field in sp, f"missing schema field: {field}"


def test_user_prompt_includes_audio_dna_concrete_numbers() -> None:
    up = prompts.build_user_prompt(
        tokens=_TOKENS,
        summary=_SUMMARY,
        audio_hash="dead",
        style=_STYLE,
        recipe=_RECIPE,
        game_params=_GAME_PARAMS,
        recent_concept_summaries=[],
    )
    assert "AUDIO DNA" in up
    # Concrete numbers must reach the LLM — without them the binding is theoretical.
    assert "350" in up   # spawn_interval_ms
    assert "14" in up    # max_concurrent
    assert "1.80" in up  # escalation_per_min, formatted as %.2f
    assert "60%" in up   # randomness_pct


def test_user_prompt_includes_mechanic_core_loop() -> None:
    up = prompts.build_user_prompt(
        tokens=_TOKENS,
        summary=_SUMMARY,
        audio_hash="dead",
        style=_STYLE,
        recipe=_RECIPE,
        game_params=_GAME_PARAMS,
        recent_concept_summaries=[],
    )
    assert "core_loop" in up
    assert "Aim deflection; chain ricochets" in up


def test_user_prompt_avoid_block_uses_recent_summaries() -> None:
    up = prompts.build_user_prompt(
        tokens=_TOKENS,
        summary=_SUMMARY,
        audio_hash="dead",
        style=_STYLE,
        recipe=_RECIPE,
        game_params=_GAME_PARAMS,
        recent_concept_summaries=["Past Game A — t1", "Past Game B — t2"],
    )
    assert "AVOID resembling" in up
    assert "Past Game A — t1" in up
    assert "Past Game B — t2" in up


def test_user_prompt_handles_empty_recent_summaries() -> None:
    up = prompts.build_user_prompt(
        tokens=_TOKENS,
        summary=_SUMMARY,
        audio_hash="dead",
        style=_STYLE,
        recipe=_RECIPE,
        game_params=_GAME_PARAMS,
        recent_concept_summaries=[],
    )
    assert "none yet" in up
