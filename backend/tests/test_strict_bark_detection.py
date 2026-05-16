"""Tests for the strict dog-detection logic in YAMNet wrapper + pipeline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from bark_to_game.audio import classify as classify_mod
from bark_to_game.audio import pipeline, yamnet

# ---- _decide_dog_like unit tests ----------------------------------------


def test_decide_below_score_floor_rejects() -> None:
    assert yamnet._decide_dog_like(0.02, "Bark", 0.02) is False


def test_decide_above_floor_with_no_non_dog_competitor_accepts() -> None:
    assert yamnet._decide_dog_like(0.10, "Animal sounds", 0.05) is True


def test_decide_dominant_speech_rejects_even_with_some_dog_score() -> None:
    # Person talking into the mic — Bark scores 0.05 (clears floor) but
    # Speech scores 0.90 (way more than 2x). Reject.
    assert yamnet._decide_dog_like(0.05, "Speech", 0.90) is False


def test_decide_dominant_speech_within_2x_accepts() -> None:
    # Borderline: Speech is top but only barely above the dog score.
    # Accept and let the user proceed.
    assert yamnet._decide_dog_like(0.20, "Speech", 0.35) is True


def test_decide_music_dominant_rejects() -> None:
    assert yamnet._decide_dog_like(0.06, "Music", 0.80) is False


# ---- pipeline integration: fake classify returns non-dog -----------------


def _silence_then_tone() -> bytes:
    """Build a WAV with one ~200ms 400 Hz tone in the middle."""
    import io

    import soundfile as sf

    sr = 16000
    silence = np.zeros(int(sr * 0.3), dtype=np.float32)
    t = np.linspace(0, 0.2, int(sr * 0.2), endpoint=False)
    tone = (0.5 * np.sin(2 * np.pi * 400 * t)).astype(np.float32)
    audio = np.concatenate([silence, tone, silence])
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_pipeline_marks_not_a_bark_when_all_segments_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the classifier judges every segment non-dog-like, pipeline returns
    detection='not_a_bark' with the dominant other class surfaced."""

    def fake_classify(_y: np.ndarray, _sr: int) -> classify_mod.Classification:
        return classify_mod.Classification(
            type="BARK",
            confidence=0.03,
            source="yamnet",
            is_dog_like=False,
            top_other_class="Speech",
        )

    monkeypatch.setattr(classify_mod, "classify", fake_classify)

    result = pipeline.analyze(_silence_then_tone())
    assert result["detection"] == "not_a_bark"
    assert result["detected_class"] == "Speech"
    assert result["tokens"] == []
    assert result["rejected_segment_count"] >= 1


def test_pipeline_marks_bark_when_at_least_one_segment_dog_like(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify(_y: np.ndarray, _sr: int) -> classify_mod.Classification:
        return classify_mod.Classification(
            type="BARK",
            confidence=0.40,
            source="yamnet",
            is_dog_like=True,
            top_other_class="Speech",
        )

    monkeypatch.setattr(classify_mod, "classify", fake_classify)

    result = pipeline.analyze(_silence_then_tone())
    assert result["detection"] == "bark"
    assert result["detected_class"] == ""
    assert len(result["tokens"]) >= 1


def test_pipeline_silent_audio_returns_silent_state(silent_audio: bytes) -> None:
    result = pipeline.analyze(silent_audio)
    assert result["detection"] == "silent"
    assert result["detected_class"] == ""
    assert result["tokens"] == []


# ---- heuristic fallback path keeps is_dog_like True ----------------------


def test_heuristic_fallback_marks_dog_like_to_avoid_breaking_offline_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If YAMNet is unavailable we can't tell — must not lock the user out."""

    def _fail(*_: Any, **__: Any) -> Any:
        raise RuntimeError("yamnet disabled")

    monkeypatch.setattr(yamnet, "classify", _fail)

    sr = 16000
    tone = (0.5 * np.sin(2 * np.pi * 400 * np.linspace(0, 0.2, int(sr * 0.2)))).astype(
        np.float32
    )
    cls = classify_mod.classify(tone, sr)
    assert cls["source"] == "heuristic"
    assert cls["is_dog_like"] is True
