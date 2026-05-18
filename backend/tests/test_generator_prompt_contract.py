"""Generator SYSTEM_PROMPT contract — Simplified Chinese + difficulty curve.

The generator's SYSTEM_PROMPT used to allow Traditional Chinese sample text
(繁體, 點擊, 開始, 再來). We saw at least one shipped game (Tide Sorter)
that rendered Traditional copy as a result. These tests pin the new rule
so a future edit can't quietly revert it.

Also pin the 3-phase difficulty curve (warm-up → standard → pressure)
so the easy-to-hard ramp survives future prompt edits.
"""

from __future__ import annotations

from bark_to_game.generate import _api_backend, _sdk_backend


_BACKENDS = (
    ("api", _api_backend.SYSTEM_PROMPT),
    ("sdk", _sdk_backend.SYSTEM_PROMPT),
)


def test_both_generator_prompts_require_simplified_chinese() -> None:
    """Tide Sorter regression: never allow Traditional in generated copy."""
    for name, sp in _BACKENDS:
        assert "Simplified Chinese" in sp or "简体中文" in sp, (
            f"{name} backend: missing Simplified Chinese requirement"
        )
        # Concrete Simplified samples to anchor model output.
        for ex in ("简体", "点击", "开始"):
            assert ex in sp, f"{name} backend: missing example {ex}"
        # Concrete Traditional forms must appear ONLY in the "don't use" sense.
        # We can't perfectly detect intent, but at minimum the prompt should
        # mention 繁體 / Traditional so the contrast is explicit.
        assert "繁體" in sp or "Traditional" in sp, (
            f"{name} backend: missing Don't-use-Traditional callout"
        )
        # Replay CTA on the fail screen uses Simplified, not Traditional.
        assert "再来一次" in sp, f"{name} backend: replay CTA must be Simplified"
        assert "再來一次" not in sp, (
            f"{name} backend: replay CTA still contains Traditional form 再來一次"
        )


def test_both_generator_prompts_require_three_phase_difficulty_curve() -> None:
    """Easy → Medium → Hard: warm-up (0–20s), standard (20–60s), pressure (60s+)."""
    for name, sp in _BACKENDS:
        assert "DIFFICULTY CURVE" in sp, f"{name}: missing DIFFICULTY CURVE section"
        # Phase markers
        for phase in ("Warm-up", "Standard", "Pressure"):
            assert phase in sp, f"{name}: missing phase '{phase}'"
        # Time markers
        for t in ("20", "60"):
            assert t in sp, f"{name}: missing time marker '{t}'"
        # Multiplier hint for the warm-up easy-mode (must be visibly easier)
        assert "× 2.0" in sp or "x 2.0" in sp, (
            f"{name}: missing warm-up spawn × 2.0 hint"
        )


def test_both_generator_prompts_keep_first_five_seconds_rule() -> None:
    """Don't regress the earlier first-5s onboarding rule."""
    for name, sp in _BACKENDS:
        assert "FIRST-FIVE-SECONDS" in sp or "first 5 seconds" in sp.lower(), (
            f"{name}: missing first-five-seconds rule"
        )
        # HUD must stay visible during play
        assert "HUD" in sp, f"{name}: missing HUD requirement"
