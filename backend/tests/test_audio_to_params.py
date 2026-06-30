"""Audio features → concrete game-parameter mapping.

The whole point of the audio-DNA layer is that a STACCATO+LOUD bark must
yield different gameplay knobs than a SPARSE+SOFT one. These tests pin the
mapping so a future tweak doesn't silently re-flatten the output.
"""

from __future__ import annotations

from typing import Any

import pytest

from bark_to_game.translate.engine import _derive_game_params


def _tokens(intensities: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "type": "BARK",
            "pitch": "MID",
            "duration": "SHORT",
            "intensity": intensity,
            "contour": "FLAT",
        }
        for intensity in intensities
    ]


def test_staccato_loud_dense_bark_maps_to_frantic_harsh() -> None:
    params = _derive_game_params(
        tokens=_tokens(["LOUD"] * 10),
        summary={"rhythm": "STACCATO", "mood": "AGITATED", "entropy": 0.85},
    )
    assert params["tempo"] == "frantic"
    assert params["density"] == "dense"
    assert params["intensity"] == "harsh"
    assert params["variability"] == "wild"
    assert params["spawn_interval_ms"] <= 400  # frantic spawn
    assert params["max_concurrent"] >= 12      # dense cap
    assert params["escalation_per_min"] >= 1.6  # harsh ramp
    assert params["randomness_pct"] >= 50       # wild jitter


def test_sparse_soft_bark_maps_to_slow_gentle() -> None:
    params = _derive_game_params(
        tokens=_tokens(["SOFT"] * 2),
        summary={"rhythm": "SPARSE", "mood": "MELANCHOLY", "entropy": 0.1},
    )
    assert params["tempo"] == "slow"
    assert params["density"] == "sparse"
    assert params["intensity"] == "gentle"
    assert params["variability"] == "steady"
    assert params["spawn_interval_ms"] >= 1200  # slow spawn
    assert params["max_concurrent"] <= 5         # sparse cap
    assert params["randomness_pct"] <= 15        # steady jitter


def test_medium_moderate_firm_bark_lands_in_middle() -> None:
    # 5 tokens, half LOUD → firm; rhythm=SPACED → medium tempo; entropy 0.5 → shifting
    params = _derive_game_params(
        tokens=_tokens(["LOUD", "NORMAL", "LOUD", "NORMAL", "NORMAL"]),
        summary={"rhythm": "SPACED", "mood": "PLAYFUL", "entropy": 0.5},
    )
    assert params["tempo"] == "medium"
    assert params["density"] == "moderate"
    assert params["intensity"] == "firm"
    assert params["variability"] == "shifting"


def test_unknown_rhythm_defaults_to_medium() -> None:
    params = _derive_game_params(
        tokens=_tokens(["NORMAL"]),
        summary={"rhythm": "WHATEVER_NEW_LABEL", "mood": "STEADY", "entropy": 0.0},
    )
    assert params["tempo"] == "medium"


def test_empty_tokens_handled() -> None:
    params = _derive_game_params(
        tokens=[],
        summary={"rhythm": "SPARSE", "entropy": 0.0},
    )
    # Must not crash, must produce sane defaults
    assert params["density"] == "sparse"
    assert params["intensity"] == "gentle"
    assert params["spawn_interval_ms"] > 0
    assert params["max_concurrent"] > 0


@pytest.mark.parametrize(
    "rhythm,expected_tempo",
    [
        ("STACCATO", "frantic"),
        ("TRIPLET", "fast"),
        ("SPACED", "medium"),
        ("SPARSE", "slow"),
    ],
)
def test_rhythm_to_tempo_mapping(rhythm: str, expected_tempo: str) -> None:
    params = _derive_game_params(
        tokens=_tokens(["NORMAL"]),
        summary={"rhythm": rhythm, "entropy": 0.4},
    )
    assert params["tempo"] == expected_tempo
