"""Per-segment acoustic features extracted with librosa."""

from __future__ import annotations

from typing import TypedDict

import librosa
import numpy as np


class SegmentFeatures(TypedDict):
    f0_mean_hz: float | None
    rms: float
    spectral_centroid_hz: float
    contour: str  # "FLAT" | "RISE" | "FALL" | "WAVY"


def _classify_contour(f0: np.ndarray) -> str:
    """Categorise the F0 contour shape.

    A linear fit gives the slope; standard deviation relative to the mean
    indicates oscillation. The order matters: WAVY first, then FLAT, then
    monotonic.
    """
    if f0.size < 3:
        return "FLAT"
    mean = float(np.mean(f0))
    if mean <= 0:
        return "FLAT"
    std_rel = float(np.std(f0) / mean)
    if std_rel > 0.25:
        return "WAVY"
    slope, _ = np.polyfit(np.arange(f0.size), f0, 1)
    slope_rel = float(slope / mean)
    if abs(slope_rel) < 0.002:
        return "FLAT"
    return "RISE" if slope_rel > 0 else "FALL"


def compute(y: np.ndarray, sr: int) -> SegmentFeatures:
    """Compute pitch, energy, spectral, and contour features for a segment."""
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=float(librosa.note_to_hz("C2")),  # 65 Hz
        fmax=float(librosa.note_to_hz("C7")),  # 2093 Hz
        sr=sr,
    )
    valid_f0 = f0[~np.isnan(f0)] if voiced_flag.any() else np.array([], dtype=np.float32)
    f0_mean: float | None = float(valid_f0.mean()) if valid_f0.size > 0 else None

    rms = float(librosa.feature.rms(y=y).mean())
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    contour = _classify_contour(valid_f0)

    return SegmentFeatures(
        f0_mean_hz=f0_mean,
        rms=rms,
        spectral_centroid_hz=centroid,
        contour=contour,
    )
