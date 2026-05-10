"""W5-#4 — LSTM 신뢰도 + 예측 분산 추정 테스트."""
from __future__ import annotations

from app.ml.forecasting import SpendForecaster


def test_no_data_returns_zero_std():
    f = SpendForecaster()
    out = f.predict([])
    assert out["predicted"] == 0
    assert out["std"] == 0.0
    assert out["mc_samples"] == 0


def test_moving_avg_provides_std_and_ci():
    f = SpendForecaster()
    out = f.predict([100.0, 200.0, 150.0, 180.0])
    assert out["method"] == "weighted_moving_avg"
    assert out["std"] > 0
    assert out["ci95_low"] <= out["predicted"] <= out["ci95_high"]
    assert out["confidence"] > 0


def test_moving_avg_constant_series_zero_std():
    f = SpendForecaster()
    out = f.predict([100.0, 100.0, 100.0])
    assert out["std"] == 0.0
    assert out["ci95_low"] == out["ci95_high"] == out["predicted"] == 100.0


def test_predict_supports_mc_samples_keyword():
    # torch 미설치/미학습 환경에서도 fallback 으로 응답하며 mc_samples=0 노출
    f = SpendForecaster()
    out = f.predict([100.0, 110.0], mc_samples=5)
    assert "mc_samples" in out
    assert "ci95_low" in out
    assert "ci95_high" in out
