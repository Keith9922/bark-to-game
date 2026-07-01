"""Orchestrate full audio -> token sequence pipeline.

Detection states (the ``detection`` field on the analysis result):
  - ``"silent"``  — peak amplitude below the silence floor; no segments
  - ``"not_a_bark"`` — segmentation found audio but no segment was dog-like
  - ``"bark"`` — at least one segment scored as dog-like; tokens populated

Non-bark segments are filtered out of the token list even when the overall
detection is ``bark``: they are usually background speech or breath between
real barks, and would pollute the translate prompt.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import librosa
import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

from bark_to_game.audio import classify, features, segmentation, tokens

SAMPLE_RATE = 16000  # YAMNet requires 16 kHz mono
SILENCE_AMPLITUDE_THRESHOLD = 1.0e-4  # below this peak, treat as silence


def _load(audio_bytes: bytes) -> np.ndarray:
    raw, raw_sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    y: np.ndarray = np.asarray(raw, dtype=np.float32)
    sr = int(raw_sr)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != SAMPLE_RATE:
        y = np.asarray(
            librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE),
            dtype=np.float32,
        )
    return y


def _session_summary(token_list: list[dict[str, Any]]) -> dict[str, Any]:
    if not token_list:
        return {"rhythm": "SILENT", "mood": "CALM", "entropy": 0.0}

    if len(token_list) >= 2:
        gaps = [
            token_list[i + 1]["start_ms"] - token_list[i]["end_ms"]
            for i in range(len(token_list) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap < 200:
            rhythm = "STACCATO"
        elif avg_gap < 500:
            rhythm = "TRIPLET"
        else:
            rhythm = "SPACED"
    else:
        rhythm = "SPARSE"

    loud_ratio = sum(1 for t in token_list if t["intensity"] == "LOUD") / len(token_list)
    if loud_ratio > 0.5:
        mood = "AGITATED"
    elif any(t["type"] in {"HOWL", "WHIMPER"} for t in token_list):
        mood = "MELANCHOLY"
    elif any(t["type"] == "YIP" for t in token_list):
        mood = "PLAYFUL"
    else:
        mood = "STEADY"

    distinct_types = {t["type"] for t in token_list}
    entropy = round(min(1.0, len(distinct_types) / 5.0), 2)

    return {"rhythm": rhythm, "mood": mood, "entropy": entropy}


def analyze(audio_bytes: bytes) -> dict[str, Any]:
    """Full pipeline: bytes -> tokens + session summary + audio hash (seed)."""
    if not audio_bytes:
        raise ValueError("empty audio buffer")

    y = _load(audio_bytes)
    duration_ms = int(y.size / SAMPLE_RATE * 1000)
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()[:16]

    # Hard silence guard: librosa.effects.split can mis-detect on uniform
    # zero/near-zero signals. Bypass segmentation if peak is essentially zero.
    peak = float(np.max(np.abs(y)))
    if peak < SILENCE_AMPLITUDE_THRESHOLD:
        return {
            "audio_hash": audio_hash,
            "duration_ms": duration_ms,
            "sample_count": int(y.size),
            "tokens": [],
            "summary": _session_summary([]),
            "detection": "silent",
            "detected_class": "",
            "rejected_segment_count": 0,
            "degraded": False,
        }

    # Peak-normalise so intensity (RMS) is gain-invariant — the same bark at a
    # different mic level lands in the same SOFT/NORMAL/LOUD bucket, and the
    # bins stop tracking recording level instead of loudness.
    y = y / peak

    intervals = segmentation.split_on_silence(y, SAMPLE_RATE)

    bark_tokens: list[dict[str, Any]] = []
    rejected_count = 0
    degraded = False
    # Track the strongest non-dog class we saw, so the front-end can tell the
    # user what was heard instead of just "not a bark".
    strongest_other_class = ""
    strongest_other_score = 0.0

    for start, end in intervals:
        segment = y[start:end]
        seg_duration_ms = int((end - start) / SAMPLE_RATE * 1000)
        feats = features.compute(segment, SAMPLE_RATE)
        cls = classify.classify(segment, SAMPLE_RATE)
        degraded = degraded or cls["degraded"]
        if not cls["is_dog_like"]:
            rejected_count += 1
            # Pick the most confident non-dog class across all rejected
            # segments so the UI can tell the user "we heard <X>".
            if (
                cls.get("top_other_class")
                and cls.get("top_other_score", 0.0) > strongest_other_score
            ):
                strongest_other_class = cls["top_other_class"]
                strongest_other_score = cls["top_other_score"]
            continue
        tok = tokens.make(feats, cls, seg_duration_ms)
        bark_tokens.append(
            {
                "start_ms": int(start / SAMPLE_RATE * 1000),
                "end_ms": int(end / SAMPLE_RATE * 1000),
                **tok,
            }
        )

    if not intervals:
        detection = "silent"
        detected_class = ""
    elif bark_tokens:
        detection = "bark"
        detected_class = ""
    else:
        detection = "not_a_bark"
        detected_class = strongest_other_class

    return {
        "audio_hash": audio_hash,
        "duration_ms": duration_ms,
        "sample_count": int(y.size),
        "tokens": bark_tokens,
        "summary": _session_summary(bark_tokens),
        "detection": detection,
        "detected_class": detected_class,
        "rejected_segment_count": rejected_count,
        "degraded": degraded,
    }
