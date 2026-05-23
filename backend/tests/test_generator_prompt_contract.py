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
        assert "× 2.0" in sp or "x 2.0" in sp or "× 0.5" in sp, (
            f"{name}: missing warm-up pacing multipliers"
        )


def test_both_generator_prompts_carry_round_one_floor_rules() -> None:
    """Regression for Neon Shepherd / 'wave 1 has 3 ghosts': prompts must
    explicitly halve round-1 quota AND mute lose path in first 20 s AND
    discourage 5+ wave wins."""
    for name, sp in _BACKENDS:
        # Halving quota (concept text may say 'three' / 'twelve' / etc.)
        assert "HALF" in sp or "half" in sp, (
            f"{name}: missing 'half the quantity for round 1' rule"
        )
        # First-round win reachable in <= 30s
        assert "30 s" in sp or "30s" in sp, (
            f"{name}: missing 30s round-1 win target"
        )
        # No-fail warm-up
        nofail_markers = ("No-fail", "no-fail", "No fail", "no fail")
        assert any(m in sp for m in nofail_markers), (
            f"{name}: missing 'no-fail warm-up' rule"
        )
        # 2-4 round win, not 5+
        assert "2–4" in sp or "2-4" in sp, (
            f"{name}: missing 'win in 2-4 rounds' guidance"
        )


def test_translate_rubric_carries_round_one_win_floor() -> None:
    """Concept design upstream of the generator must avoid 5+ wave wins,
    3+ minute survives, or 'twelve to win' in round 1."""
    from bark_to_game.translate import prompts
    sp = prompts.SYSTEM_PROMPT
    # "FIRST WIN MOMENT" may wrap across lines — match the start of the phrase.
    assert "FIRST WIN" in sp or "first win" in sp.lower()
    assert "HALF" in sp or "half" in sp
    assert "WIN BUDGET" in sp or "win budget" in sp.lower()
    assert "2–4" in sp or "2-4" in sp


def test_both_generator_prompts_keep_first_five_seconds_rule() -> None:
    """Don't regress the earlier first-5s onboarding rule."""
    for name, sp in _BACKENDS:
        assert "FIRST-FIVE-SECONDS" in sp or "first 5 seconds" in sp.lower(), (
            f"{name}: missing first-five-seconds rule"
        )
        # HUD must stay visible during play
        assert "HUD" in sp, f"{name}: missing HUD requirement"


def test_both_generator_prompts_carry_mobile_first_rules() -> None:
    """Default to desktop is dead. The prompt must force mobile-first."""
    for name, sp in _BACKENDS:
        assert "MOBILE-FIRST" in sp, f"{name}: missing MOBILE-FIRST section"
        # Concrete, non-negotiable mobile constraints:
        assert "44" in sp, f"{name}: missing 44px tap-target rule"
        assert "hover" in sp.lower(), f"{name}: missing no-hover rule"
        assert "touch-action: manipulation" in sp, (
            f"{name}: missing tap-delay-killer rule"
        )
        assert "safe-area-inset" in sp, f"{name}: missing safe-area rule"


def test_both_generator_prompts_carry_ui_polish_rules() -> None:
    """Forces the generator past 'student-project' UI."""
    for name, sp in _BACKENDS:
        assert "UI POLISH" in sp, f"{name}: missing UI POLISH section"
        for needle in ("breathe", "8-px"):
            assert needle in sp, f"{name}: missing polish keyword {needle!r}"


def test_translate_diversity_axes_include_control_surface() -> None:
    """Translate prompt lists 'control surface' so phone-friendly input wins."""
    from bark_to_game.translate import prompts
    assert "CONTROL SURFACE" in prompts.SYSTEM_PROMPT


def test_translate_prompt_carries_polish_bar() -> None:
    """Concepts that require hover / multi-touch / precise drawing must be killed
    upstream so the generator never has to fight them downstream."""
    from bark_to_game.translate import prompts
    sp = prompts.SYSTEM_PROMPT
    assert "POLISH BAR" in sp
    for word in ("hover", "multi-touch", "thumb"):
        assert word in sp.lower(), f"missing polish-bar word: {word!r}"


def test_translate_prompt_asks_for_three_candidates_not_five() -> None:
    """Five candidates × 11 fields was making the upstream model timeout on
    busy aipaibox channels (May-23 prod 120 s ReadTimeout). Three is enough
    for Verbalized Sampling diversity since we only ship the top pick."""
    from bark_to_game.translate import prompts
    sp = prompts.SYSTEM_PROMPT
    assert "exactly 3 candidates" in sp, "translate must ask for 3 candidates"
    assert "exactly 5 candidates" not in sp, (
        "translate still asks for 5 — should be 3 to keep output small enough "
        "that a single Claude call returns within the upstream timeout window"
    )


def test_both_generator_prompts_carry_code_self_check_rules() -> None:
    """Regression for crashed games (uninitialised player/items vars) and the
    catch-game logic bug (penalising missing non-target items). The prompt
    must explicitly list both bug shapes so the model self-checks before
    closing the html block."""
    for name, sp in _BACKENDS:
        # Section anchor — easy to grep if someone reorders.
        assert "CODE SELF-CHECK" in sp, f"{name}: missing CODE SELF-CHECK section"

        # 15a: init at declaration. Must call out the bare `let player;` anti-pattern
        # so the model doesn't slide into the same lazy init.
        assert "let player;" in sp or "let items;" in sp, (
            f"{name}: missing 'don't declare bare, init later' anti-pattern example"
        )

        # 15b: catch/sort/match non-target = free. The bug we shipped twice.
        assert "non-target" in sp.lower(), (
            f"{name}: missing 'non-target items are FREE' rule"
        )

        # 15c: mental round-1 dry-run before output
        assert "dry-run" in sp.lower() or "Round-1 dry-run" in sp, (
            f"{name}: missing round-1 mental dry-run requirement"
        )
