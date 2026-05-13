"""W8-#6 — OR 결합 FP 비용 평가 테스트."""
from __future__ import annotations

from app.services.fp_cost_analyzer import (
    RuleStat,
    expected_fp_count_per_day,
    kappa_redundancy,
    or_fp_combined,
    recommend_disable,
)


def test_or_fp_empty_zero():
    assert or_fp_combined([]) == 0.0


def test_or_fp_single_returns_same():
    r = RuleStat("a", fp_rate=0.05, tp_rate=0.8, trigger_count=100)
    assert abs(or_fp_combined([r]) - 0.05) < 1e-9


def test_or_fp_two_independent():
    rs = [
        RuleStat("a", fp_rate=0.1, tp_rate=0.5, trigger_count=100),
        RuleStat("b", fp_rate=0.1, tp_rate=0.5, trigger_count=100),
    ]
    # 1 - 0.9 * 0.9 = 0.19
    assert abs(or_fp_combined(rs) - 0.19) < 1e-9


def test_expected_fp_per_day():
    rs = [
        RuleStat("a", fp_rate=0.01, tp_rate=0.6, trigger_count=100, cost_per_fp_krw=10000),
        RuleStat("b", fp_rate=0.02, tp_rate=0.5, trigger_count=100, cost_per_fp_krw=5000),
    ]
    out = expected_fp_count_per_day(rs, daily_traffic=100_000)
    assert out["per_rule"][0]["fp_per_day"] == 1000
    assert out["per_rule"][0]["cost_krw_per_day"] == 1000 * 10000
    assert out["sum_fp_naive"] == 3000
    # OR combined < sum (overlap correction)
    assert out["or_combined_fp_per_day"] < out["sum_fp_naive"]


def test_recommend_disable_flags_high_cost_low_tp():
    rs = [
        RuleStat("noisy", fp_rate=0.1, tp_rate=0.02, trigger_count=1000, cost_per_fp_krw=10000),
        RuleStat("good", fp_rate=0.01, tp_rate=0.7, trigger_count=1000, cost_per_fp_krw=10000),
    ]
    out = recommend_disable(rs)
    assert any(r["rule_id"] == "noisy" for r in out)
    assert all(r["rule_id"] != "good" for r in out)


def test_recommend_disable_empty():
    assert recommend_disable([]) == []


def test_kappa_zero_for_single_rule():
    rs = [RuleStat("a", fp_rate=0.1, tp_rate=0.5, trigger_count=10)]
    assert kappa_redundancy(rs) == 0.0


def test_kappa_high_when_rules_overlap():
    # 같은 fp_rate 두 룰 → 약간 중복
    rs = [
        RuleStat("a", fp_rate=0.1, tp_rate=0.5, trigger_count=10),
        RuleStat("b", fp_rate=0.1, tp_rate=0.5, trigger_count=10),
    ]
    # sum=0.2, or=0.19 → redundancy = (0.2 - 0.19)/0.2 = 0.05
    k = kappa_redundancy(rs)
    assert 0.0 < k < 0.1
