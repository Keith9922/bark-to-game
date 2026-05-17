"""Classification orchestrator: YAMNet primary, heuristic fallback.

YAMNet is the source of truth for real dog audio AND for non-dog rejection.
For synthetic test audio, unavailable TF, or any other error we fall back to
a feature-based heuristic so the pipeline never breaks the user flow.

When falling back to the heuristic we cannot tell dog-like from non-dog-like
(it would require its own classifier). To keep the pipeline alive we mark
heuristic segments as dog-like — the upstream silence guard already rejects
the obviously-empty case.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
from loguru import logger

from bark_to_game.audio import yamnet


class Classification(TypedDict):
    type: str
    confidence: float  # the dog-class score (not the top global score)
    source: str  # "yamnet" | "heuristic"
    is_dog_like: bool
    top_other_class: str  # YAMNet display name; "" for heuristic
    top_other_score: float  # YAMNet score of top_other_class; 0.0 for heuristic


def _heuristic(y: np.ndarray, sr: int) -> Classification:
    """Pure-feature classification used as fallback.

    Uses duration + estimated F0 to pick the most plausible token type.
    Confidence is fixed at 0.5 to signal "guessed".
    """
    import librosa

    duration_s = float(y.size / sr)
    f0, _, _ = librosa.pyin(y, fmin=80.0, fmax=2000.0, sr=sr)
    valid = f0[~np.isnan(f0)]
    if valid.size == 0:
        return Classification(
            type="BARK",
            confidence=0.3,
            source="heuristic",
            is_dog_like=True,
            top_other_class="",
            top_other_score=0.0,
        )

    mean_f0 = float(np.mean(valid))
    if duration_s > 0.7:
        token_type = "HOWL"
    elif mean_f0 > 700:
        token_type = "YIP"
    elif mean_f0 < 180:
        token_type = "GROWL"
    else:
        token_type = "BARK"
    return Classification(
        type=token_type,
        confidence=0.5,
        source="heuristic",
        is_dog_like=True,
        top_other_class="",
        top_other_score=0.0,
    )


def classify(y: np.ndarray, sr: int) -> Classification:
    """Try YAMNet first; fall back to heuristic on any error."""
    try:
        result = yamnet.classify(y, sr)
        return Classification(
            type=result["type"],
            confidence=result["confidence"],
            source="yamnet",
            is_dog_like=result["is_dog_like"],
            top_other_class=result["top_other_class"],
            top_other_score=result["top_other_score"],
        )
    except Exception as exc:
        # ``error`` not ``warning``: in production this means the strict
        # dog-detection just got silently disabled (the heuristic accepts
        # everything). Loud logs make a stuck dependency visible in ops.
        logger.error(f"YAMNet classification failed, falling back to heuristic: {exc!r}")
        return _heuristic(y, sr)
