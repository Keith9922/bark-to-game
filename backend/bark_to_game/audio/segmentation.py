"""Energy-based silence segmentation."""

from __future__ import annotations

import librosa
import numpy as np


def split_on_silence(
    y: np.ndarray,
    sr: int,
    top_db: float = 30.0,
    min_duration_ms: int = 60,
) -> list[tuple[int, int]]:
    """Return list of (start_sample, end_sample) for non-silent regions.

    `top_db` is the threshold (in dB below reference) under which audio is
    considered silence. `min_duration_ms` filters out very short blips.
    """
    if y.size == 0:
        return []
    intervals = librosa.effects.split(y, top_db=top_db)
    min_samples = int(min_duration_ms * sr / 1000)
    return [(int(s), int(e)) for s, e in intervals if (e - s) >= min_samples]
