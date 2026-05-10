"""W5-#3 — 사용자별 적응형 step-up 임계값 테스트."""
from __future__ import annotations

from app.services.stepup_threshold import (
    _GLOBAL_DEFAULT,
    _MIN_HISTORY,
    AdaptiveStepupThreshold,
    adaptive_stepup,
    get_adaptive_threshold,
    record_risk_score,
)


def setup_function(_):
    adaptive_stepup.reset()


def test_no_history_uses_global():
    out = AdaptiveStepupThreshold().get_threshold("u1")
    assert out["threshold"] == _GLOBAL_DEFAULT
    assert out["source"] == "global_default"


def test_below_min_history_uses_global():
    a = AdaptiveStepupThreshold()
    for i in range(_MIN_HISTORY - 1):
        a.record_score("u1", 0.2)
    out = a.get_threshold("u1")
    assert out["source"] == "global_default"


def test_zero_std_falls_back_to_global():
    a = AdaptiveStepupThreshold()
    for _ in range(_MIN_HISTORY + 5):
        a.record_score("u1", 0.2)
    out = a.get_threshold("u1")
    assert out["source"] == "global_default_zero_std"
    assert out["std"] == 0.0


def test_low_variance_user_low_adaptive_threshold():
    a = AdaptiveStepupThreshold()
    # 평균 0.2, 작은 분산
    scores = [0.18, 0.20, 0.22, 0.19, 0.21, 0.20, 0.18, 0.22, 0.19, 0.21]
    for s in scores:
        a.record_score("low_variance", s)
    out = a.get_threshold("low_variance")
    assert out["source"] == "adaptive"
    # mean(~0.2) + 2*std(~0.015) ≈ 0.23 → clamp 0.4
    assert out["threshold"] == 0.4
    assert out["mean"] < 0.25


def test_high_variance_user_higher_threshold():
    a = AdaptiveStepupThreshold()
    scores = [0.1, 0.5, 0.2, 0.7, 0.3, 0.6, 0.15, 0.65, 0.25, 0.55]
    for s in scores:
        a.record_score("high_variance", s)
    out = a.get_threshold("high_variance")
    assert out["source"] == "adaptive"
    # 큰 std → raw 가 1.0 근처 → upper 0.9 클립
    assert out["threshold"] >= 0.6
    assert out["threshold"] <= 0.9


def test_invalid_score_ignored():
    a = AdaptiveStepupThreshold()
    a.record_score("u", "not-float")
    a.record_score("u", float("nan"))
    out = a.get_threshold("u")
    assert out["n"] == 0


def test_singleton_helpers():
    for _ in range(_MIN_HISTORY + 1):
        record_risk_score("user-x", 0.2)
    record_risk_score("user-x", 0.5)
    th = get_adaptive_threshold("user-x")
    assert 0.4 <= th <= 0.9
