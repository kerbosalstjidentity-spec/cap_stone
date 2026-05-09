"""W9-#8 — LSTM 클램프 발생률 메트릭 + seed 훅."""
from __future__ import annotations

import os

from app.ml.forecasting import (
    _record_clamp,
    get_clamp_health,
    reset_clamp_stats,
    seed_lstm,
)


def test_clamp_health_initial():
    reset_clamp_stats()
    h = get_clamp_health()
    assert h["total_predictions"] == 0
    assert h["clamped"] == 0
    assert h["clamp_rate"] == 0.0
    assert h["threshold_warning"] is False


def test_record_clamp_accumulates():
    reset_clamp_stats()
    _record_clamp(100.0, False)
    _record_clamp(-50.0, True)
    _record_clamp(-10.0, True)
    h = get_clamp_health()
    assert h["total_predictions"] == 3
    assert h["clamped"] == 2
    assert h["clamp_rate"] == 0.6667


def test_threshold_warning_above_5pct():
    reset_clamp_stats()
    for _ in range(95):
        _record_clamp(100, False)
    for _ in range(6):
        _record_clamp(-1, True)
    h = get_clamp_health()
    assert h["clamp_rate"] >= 0.05
    assert h["threshold_warning"] is True


def test_seed_default():
    os.environ.pop("LSTM_SEED", None)
    s = seed_lstm()
    assert s == 42


def test_seed_env_override():
    os.environ["LSTM_SEED"] = "123"
    try:
        assert seed_lstm() == 123
    finally:
        os.environ.pop("LSTM_SEED", None)


def test_seed_invalid_falls_back():
    os.environ["LSTM_SEED"] = "abc"
    try:
        assert seed_lstm() == 42
    finally:
        os.environ.pop("LSTM_SEED", None)
