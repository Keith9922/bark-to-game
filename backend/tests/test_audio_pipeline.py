"""End-to-end pipeline tests using synthetic audio (heuristic classifier)."""

from __future__ import annotations

import pytest

from bark_to_game.audio.pipeline import analyze


def test_short_bark_yields_one_segment(short_bark_audio: bytes, force_heuristic: None) -> None:
    result = analyze(short_bark_audio)
    assert result["duration_ms"] > 0
    assert len(result["tokens"]) == 1
    tok = result["tokens"][0]
    assert tok["type"] in {"BARK", "HOWL", "YIP", "GROWL", "WHIMPER"}
    assert tok["duration"] in {"SHORT", "MED", "LONG"}
    assert tok["intensity"] in {"SOFT", "NORMAL", "LOUD"}
    assert tok["source"] == "heuristic"


def test_multi_segment_yields_variety(multi_segment_audio: bytes, force_heuristic: None) -> None:
    result = analyze(multi_segment_audio)
    assert len(result["tokens"]) >= 2, "expected at least 2 detected segments"
    pitches = {t["pitch"] for t in result["tokens"]}
    intensities = {t["intensity"] for t in result["tokens"]}
    # different tones should produce different bins (high signal of token diversity)
    assert len(pitches | intensities) >= 2


def test_silent_audio_yields_no_segments(silent_audio: bytes, force_heuristic: None) -> None:
    result = analyze(silent_audio)
    assert result["tokens"] == []
    assert result["summary"]["rhythm"] == "SILENT"
    assert result["summary"]["mood"] == "CALM"


def test_audio_hash_is_deterministic(short_bark_audio: bytes, force_heuristic: None) -> None:
    a = analyze(short_bark_audio)
    b = analyze(short_bark_audio)
    assert a["audio_hash"] == b["audio_hash"]
    assert len(a["audio_hash"]) == 16


def test_empty_audio_raises(force_heuristic: None) -> None:
    with pytest.raises(ValueError, match="empty"):
        analyze(b"")
