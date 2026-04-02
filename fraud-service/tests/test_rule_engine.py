"""Rule Engine 단위 테스트."""
import pytest
from app.services.rule_engine import (
    RuleEngine,
    AmountBlockRule,
    AmountReviewRule,
    TimeRiskRule,
    VelocityRule,
    ForeignIpRule,
    AmountSpikeRule,
    SplitTransactionRule,
)
from app.services.profile_store import UserProfile


def _profile(**kwargs) -> UserProfile:
    defaults = dict(
        user_id="u1", tx_count=10, total_amount=500_000,
        avg_amount=50_000, max_amount=200_000,
        peak_hour=14, merchant_diversity=5,
        velocity={"1m": 0, "5m": 0, "15m": 0},
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


# --- 개별 규칙 ---

def test_amount_block_fires():
    r = AmountBlockRule(block_threshold=1_000_000)
    result = r.evaluate({"amount": 1_000_000}, None)
    assert result is not None
    assert result.action == "BLOCK"


def test_amount_block_no_fire():
    r = AmountBlockRule(block_threshold=1_000_000)
    assert r.evaluate({"amount": 999_999}, None) is None


def test_amount_review_fires():
    r = AmountReviewRule(review_threshold=500_000)
    result = r.evaluate({"amount": 500_000}, None)
    assert result.action == "REVIEW"


def test_time_risk_fires_in_window():
    r = TimeRiskRule(start_hour=2, end_hour=5, amount_threshold=100_000)
    result = r.evaluate({"hour": 3, "amount": 200_000}, None)
    assert result is not None
    assert result.action == "REVIEW"


def test_time_risk_no_fire_outside_window():
    r = TimeRiskRule(start_hour=2, end_hour=5, amount_threshold=100_000)
    assert r.evaluate({"hour": 10, "amount": 200_000}, None) is None


def test_time_risk_no_fire_low_amount():
    r = TimeRiskRule(start_hour=2, end_hour=5, amount_threshold=100_000)
    assert r.evaluate({"hour": 3, "amount": 50_000}, None) is None


def test_velocity_rule_fires():
    r = VelocityRule(window_minutes=5, max_count=3)
    p = _profile(velocity={"1m": 2, "5m": 5, "15m": 5})
    result = r.evaluate({}, p)
    assert result is not None
    assert result.action == "BLOCK"


def test_velocity_rule_no_fire():
    r = VelocityRule(window_minutes=5, max_count=3)
    p = _profile(velocity={"1m": 0, "5m": 2, "15m": 2})
    assert r.evaluate({}, p) is None


def test_velocity_rule_no_profile():
    r = VelocityRule(window_minutes=5, max_count=3)
    assert r.evaluate({}, None) is None


def test_foreign_ip_fires():
    r = ForeignIpRule(amount_threshold=100_000)
    result = r.evaluate({"is_foreign_ip": True, "amount": 200_000, "ip": "1.2.3.4"}, None)
    assert result is not None
    assert result.action == "REVIEW"


def test_foreign_ip_no_fire_low_amount():
    r = ForeignIpRule(amount_threshold=100_000)
    assert r.evaluate({"is_foreign_ip": True, "amount": 50_000}, None) is None


def test_amount_spike_fires():
    r = AmountSpikeRule(spike_multiplier=3.0, min_avg=10_000)
    p = _profile(avg_amount=50_000)
    result = r.evaluate({"amount": 200_000}, p)
    assert result is not None
    assert result.action == "SOFT_REVIEW"


def test_amount_spike_no_fire_low_avg():
    r = AmountSpikeRule(spike_multiplier=3.0, min_avg=10_000)
    p = _profile(avg_amount=5_000)  # min_avg 미만
    assert r.evaluate({"amount": 200_000}, p) is None


def test_split_txn_fires():
    r = SplitTransactionRule(amount_max=100_000, min_count=3)
    p = _profile(velocity={"1m": 5, "5m": 5, "15m": 5})
    result = r.evaluate({"amount": 50_000}, p)
    assert result is not None
    assert result.action == "REVIEW"


# --- RuleEngine 통합 ---

def test_engine_strongest_action_is_block():
    engine = RuleEngine()
    # BLOCK 유발 조건: 금액 6백만
    results = engine.evaluate_all({"amount": 6_000_000, "score": 0.1}, None)
    action, _ = engine.get_strongest(results)
    assert action == "BLOCK"


def test_engine_empty_results_pass():
    engine = RuleEngine()
    action, rule_ids = engine.get_strongest([])
    assert action == "PASS"
    assert rule_ids == ""


def test_engine_toggle_disables_rule():
    engine = RuleEngine()
    # AMOUNT_BLOCK 비활성화
    engine.toggle_rule("AMOUNT_BLOCK")
    results = engine.evaluate_all({"amount": 9_000_000, "score": 0.1}, None)
    actions = [r.action for r in results]
    assert "BLOCK" not in [r.action for r in results if r.rule_id == "AMOUNT_BLOCK"]
    # 다시 활성화
    engine.toggle_rule("AMOUNT_BLOCK")


def test_engine_list_rules_returns_all():
    engine = RuleEngine()
    rules = engine.list_rules()
    rule_ids = {r["rule_id"] for r in rules}
    assert "AMOUNT_BLOCK" in rule_ids
    assert "VELOCITY_FREQ" in rule_ids
    assert "FOREIGN_IP" in rule_ids
