"""Phase 1 · E — audio-accuracy improvements.

Covers: gain-invariant intensity (peak normalisation), explicit UNKNOWN pitch
for unvoiced segments, and the heuristic-fallback non-bark gate + degraded flag.
"""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

from bark_to_game.audio import classify, tokens
from bark_to_game.audio.features import SegmentFeatures
from bark_to_game.audio.pipeline import analyze

SR = 16000


def _wav(y: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, y.astype(np.float32), SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _tone(freq: float, dur: float, amp: float) -> np.ndarray:
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _feats(f0: float | None) -> SegmentFeatures:
    return SegmentFeatures(f0_mean_hz=f0, rms=0.2, spectral_centroid_hz=1000.0, contour="FLAT")


def _cls() -> classify.Classification:
    return classify.Classification(
        type="BARK",
        confidence=0.5,
        source="heuristic",
        is_dog_like=True,
        top_other_class="",
        top_other_score=0.0,
        degraded=True,
    )


def test_unknown_pitch_when_f0_missing() -> None:
    assert tokens.make(_feats(None), _cls(), 300)["pitch"] == "UNKNOWN"


def test_known_pitch_still_binned() -> None:
    assert tokens.make(_feats(150.0), _cls(), 300)["pitch"] == "LOW"
    assert tokens.make(_feats(300.0), _cls(), 300)["pitch"] == "MID"
    assert tokens.make(_feats(800.0), _cls(), 300)["pitch"] == "HIGH"


def test_intensity_is_gain_invariant(force_heuristic: None) -> None:
    quiet = analyze(_wav(_tone(400, 0.5, 0.15)))
    loud = analyze(_wav(_tone(400, 0.5, 0.9)))
    assert quiet["tokens"] and loud["tokens"]
    assert quiet["tokens"][0]["intensity"] == loud["tokens"][0]["intensity"]


def test_heuristic_rejects_pitchless_noise() -> None:
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(SR // 2) * 0.3).astype(np.float32)
    result = classify._heuristic(noise, SR)
    assert result["is_dog_like"] is False
    assert result["degraded"] is True


def test_heuristic_accepts_pitched_tone() -> None:
    result = classify._heuristic(_tone(400, 0.3, 0.5), SR)
    assert result["is_dog_like"] is True
    assert result["degraded"] is True


def test_response_carries_degraded_flag(force_heuristic: None) -> None:
    result = analyze(_wav(_tone(400, 0.3, 0.5)))
    assert result["degraded"] is True
