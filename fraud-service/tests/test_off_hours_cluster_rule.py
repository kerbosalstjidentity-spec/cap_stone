"""W7.5-#3 — OffHoursClusterRule (시간대 외 거래 군집 탐지) 테스트."""
from __future__ import annotations

from app.services.policy_merge import classify_fraud_type
from app.services.profile_store import UserProfile
from app.services.rule_engine import OffHoursClusterRule


def _profile(tx_count: int, hour_hist: dict[int, int], avg: float = 50_000) -> UserProfile:
    return UserProfile(
        user_id="u_test",
        tx_count=tx_count,
        avg_amount=avg,
        hour_histogram=hour_hist,
    )


def test_off_hours_never_seen_hour_review():
    """평소 09~18시 활동 사용자가 새벽 3시에 거래 → REVIEW."""
    rule = OffHoursClusterRule(min_history=20, off_hours_threshold=0.05, amount_threshold=100_000)
    profile = _profile(50, {h: 5 for h in range(9, 19)})  # 9~18시 50건
    res = rule.evaluate({"hour": 3, "amount": 500_000}, profile=profile)
    assert res is not None
    assert res.action == "REVIEW"
    assert res.rule_id == "OFF_HOURS_CLUSTER"


def test_off_hours_low_rate_soft_review():
    """평소 거의 안 쓰는 시간대(2%)에 거래 → SOFT_REVIEW."""
    rule = OffHoursClusterRule(min_history=20, off_hours_threshold=0.05, amount_threshold=100_000)
    # 100건 중 02시는 2건 (2%)
    hist = {h: 0 for h in range(24)}
    for h in range(9, 18):
        hist[h] = 10  # 90건 (9~17시 9시간)
    hist[10] = 18  # +8 = 98건
    hist[2] = 2   # 2건 = 2%
    profile = _profile(sum(hist.values()), hist)
    res = rule.evaluate({"hour": 2, "amount": 300_000}, profile=profile)
    assert res is not None
    assert res.action == "SOFT_REVIEW"


def test_off_hours_active_hour_skips():
    """평소 활동 시간대(20% 이상) 거래 → 미발동."""
    rule = OffHoursClusterRule()
    profile = _profile(50, {h: 5 for h in range(9, 19)})
    assert rule.evaluate({"hour": 12, "amount": 500_000}, profile=profile) is None


def test_off_hours_skips_cold_start():
    """history 부족 시 미발동 (false-positive 방어)."""
    rule = OffHoursClusterRule(min_history=20)
    profile = _profile(5, {12: 5})
    assert rule.evaluate({"hour": 3, "amount": 500_000}, profile=profile) is None


def test_off_hours_skips_low_amount():
    """소액(< amount_threshold)은 미발동."""
    rule = OffHoursClusterRule(amount_threshold=100_000)
    profile = _profile(50, {h: 5 for h in range(9, 19)})
    assert rule.evaluate({"hour": 3, "amount": 5_000}, profile=profile) is None


def test_off_hours_skips_no_profile():
    rule = OffHoursClusterRule()
    assert rule.evaluate({"hour": 3, "amount": 500_000}, profile=None) is None


def test_off_hours_skips_empty_histogram():
    rule = OffHoursClusterRule(min_history=20)
    profile = _profile(50, {})
    assert rule.evaluate({"hour": 3, "amount": 500_000}, profile=profile) is None


def test_off_hours_uses_timestamp_when_hour_missing():
    """hour 키 없을 때 timestamp 에서 추출."""
    rule = OffHoursClusterRule()
    profile = _profile(50, {h: 5 for h in range(9, 19)})
    res = rule.evaluate(
        {"timestamp": "2026-05-07T03:15:00", "amount": 500_000},
        profile=profile,
    )
    assert res is not None
    assert res.action == "REVIEW"


def test_off_hours_invalid_hour_skips():
    rule = OffHoursClusterRule()
    profile = _profile(50, {h: 5 for h in range(9, 19)})
    assert rule.evaluate({"hour": -1, "amount": 500_000}, profile=profile) is None
    assert rule.evaluate({"hour": 99, "amount": 500_000}, profile=profile) is None


def test_classify_fraud_type_off_hours():
    """OFF_HOURS_CLUSTER → ACCOUNT_TAKEOVER."""
    assert classify_fraud_type(["OFF_HOURS_CLUSTER"]) == "ACCOUNT_TAKEOVER"
    # 그래프 룰과 동시 발동 시 MONEY_MULE 우선
    assert classify_fraud_type(["OFF_HOURS_CLUSTER", "MONEY_MULE_HUB"]) == "MONEY_MULE"
