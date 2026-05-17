"""Test fixtures: synthetic audio generators + filesystem isolation.

The ``_isolate_data_dirs`` fixture is autouse so every test that touches
disk (history, archive, sessions, audio, generated games) writes into a
per-test tmp dir instead of the project's real ``data/`` tree. Without
this, a test that POSTs to /api/game/generate with ``session_id="route-test"``
would create real entries in ``data/history/route-test.json`` and
``data/sessions/index.json`` — pollution that bled into the live UI.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 16000


def _tone(freq_hz: float, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0, duration_s, int(SR * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


@pytest.fixture
def short_bark_audio() -> bytes:
    """200 ms tone at 400 Hz — should produce one short MID-pitch token."""
    return _wav_bytes(_tone(400, 0.2))


@pytest.fixture
def multi_segment_audio() -> bytes:
    """Three tones at different pitches/durations separated by silence."""
    silence = np.zeros(int(SR * 0.3), dtype=np.float32)
    s1 = _tone(300, 0.15, amplitude=0.6)  # mid, short
    s2 = _tone(800, 0.6, amplitude=0.3)  # high, long, soft
    s3 = _tone(150, 0.1, amplitude=0.7)  # low, very short, loud
    return _wav_bytes(np.concatenate([silence, s1, silence, s2, silence, s3, silence]))


@pytest.fixture
def silent_audio() -> bytes:
    """1 s of silence — pipeline should report no segments."""
    return _wav_bytes(np.zeros(SR, dtype=np.float32))


@pytest.fixture(autouse=True)
def _isolate_data_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect every data dir to a per-test tmp dir."""
    from bark_to_game import paths
    from bark_to_game.history import manager as history_manager
    from bark_to_game.sessions import manager as session_manager
    from bark_to_game.translate import archive as translate_archive

    test_data = tmp_path / "data"
    test_data.mkdir()
    for name in ("history", "archive", "audio", "sessions", "generated-games"):
        (test_data / name).mkdir()

    # paths module — the source of truth other modules import from
    monkeypatch.setattr(paths, "DATA_DIR", test_data)
    monkeypatch.setattr(paths, "HISTORY_DIR", test_data / "history")
    monkeypatch.setattr(paths, "AUDIO_DIR", test_data / "audio")
    monkeypatch.setattr(paths, "GENERATED_GAMES_DIR", test_data / "generated-games")

    # Re-bind constants in modules that captured them at import time.
    monkeypatch.setattr(history_manager, "HISTORY_DIR", test_data / "history")
    monkeypatch.setattr(history_manager, "AUDIO_DIR", test_data / "audio")
    monkeypatch.setattr(session_manager, "SESSIONS_DIR", test_data / "sessions")
    monkeypatch.setattr(session_manager, "INDEX_PATH", test_data / "sessions" / "index.json")
    monkeypatch.setattr(translate_archive, "ARCHIVE_DIR", test_data / "archive")


@pytest.fixture
def force_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip YAMNet (slow / model download) and force the heuristic classifier.

    Used by all pipeline tests so they stay fast and deterministic.
    """
    from bark_to_game.audio import yamnet

    def _raise(*_: object, **__: object) -> object:
        raise RuntimeError("yamnet disabled in tests")

    monkeypatch.setattr(yamnet, "classify", _raise)
