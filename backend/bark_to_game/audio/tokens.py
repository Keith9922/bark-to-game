"""Compound token construction from features + classification."""

from __future__ import annotations

from typing import TypedDict

from bark_to_game.audio.classify import Classification
from bark_to_game.audio.features import SegmentFeatures

# (lower_inclusive, upper_exclusive, label)
_PITCH_BINS: tuple[tuple[float, float, str], ...] = (
    (0.0, 200.0, "LOW"),
    (200.0, 500.0, "MID"),
    (500.0, 20000.0, "HIGH"),
)
_DURATION_BINS: tuple[tuple[float, float, str], ...] = (
    (0.0, 200.0, "SHORT"),
    (200.0, 700.0, "MED"),
    (700.0, 1.0e9, "LONG"),
)
_INTENSITY_BINS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.05, "SOFT"),
    (0.05, 0.15, "NORMAL"),
    (0.15, 10.0, "LOUD"),
)


def _bin(value: float | None, bins: tuple[tuple[float, float, str], ...]) -> str:
    if value is None:
        return bins[0][2]
    for low, high, label in bins:
        if low <= value < high:
            return label
    return bins[-1][2]


class Token(TypedDict):
    type: str
    pitch: str
    duration: str
    intensity: str
    contour: str
    confidence: float
    source: str


def make(
    features: SegmentFeatures,
    classification: Classification,
    duration_ms: int,
) -> Token:
    return Token(
        type=classification["type"],
        pitch=_bin(features["f0_mean_hz"], _PITCH_BINS),
        duration=_bin(float(duration_ms), _DURATION_BINS),
        intensity=_bin(features["rms"], _INTENSITY_BINS),
        contour=features["contour"],
        confidence=classification["confidence"],
        source=classification["source"],
    )
