"""W7.5-#1 — BalanceDrainRule (잔액 급변 패턴) 테스트."""
from __future__ import annotations

from app.services.policy_merge import classify_fraud_type
from app.services.rule_engine import BalanceDrainRule


def test_drain_fires_high_ratio_high_amount():
    rule = BalanceDrainRule()
    tx = {
        "type": "CASH_OUT",
        "amount": 1_950_000,
        "oldbalanceOrg": 2_000_000,
        "newbalanceOrig": 50_000,
    }
    res = rule.evaluate(tx, profile=None)
    assert res is not None
    assert res.action == "BLOCK"
    assert res.rule_id == "BALANCE_DRAIN"


def test_drain_skips_partial_use():
    rule = BalanceDrainRule()
    tx = {
        "type": "CASH_OUT",
        "amount": 500_000,
        "oldbalanceOrg": 1_000_000,
        "newbalanceOrig": 500_000,  # 50% drain
    }
    assert rule.evaluate(tx, profile=None) is None


def test_drain_skips_low_amount():
    """drain 95% 지만 amount 가 임계 미만 → 미발동."""
    rule = BalanceDrainRule(amount_threshold=500_000)
    tx = {
        "type": "CASH_OUT",
        "amount": 100_000,  # below threshold
        "oldbalanceOrg": 200_000,
        "newbalanceOrig": 5_000,
    }
    assert rule.evaluate(tx, profile=None) is None


def test_drain_skips_zero_old_balance():
    rule = BalanceDrainRule()
    tx = {
        "type": "CASH_OUT",
        "amount": 1_000_000,
        "oldbalanceOrg": 0,
        "newbalanceOrig": 0,
    }
    assert rule.evaluate(tx, profile=None) is None


def test_drain_skips_below_min_old_balance():
    rule = BalanceDrainRule(min_old_balance=100_000)
    tx = {
        "type": "CASH_OUT",
        "amount": 600_000,
        "oldbalanceOrg": 50_000,
        "newbalanceOrig": 0,
    }
    assert rule.evaluate(tx, profile=None) is None


def test_drain_skips_payment_type():
    rule = BalanceDrainRule()
    tx = {
        "type": "PAYMENT",
        "amount": 1_950_000,
        "oldbalanceOrg": 2_000_000,
        "newbalanceOrig": 50_000,
    }
    assert rule.evaluate(tx, profile=None) is None


def test_drain_accepts_newbalanceOrg_alias():
    """newbalanceOrg (Orig 가 아닌) 별칭만 있어도 동작."""
    rule = BalanceDrainRule()
    tx = {
        "type": "CASH_OUT",
        "amount": 1_950_000,
        "oldbalanceOrg": 2_000_000,
        "newbalanceOrg": 50_000,
    }
    res = rule.evaluate(tx, profile=None)
    assert res is not None
    assert res.action == "BLOCK"


def test_drain_fires_without_type_field():
    """type 미지정 시(레거시 페이로드)에도 발동 — type 필터는 명시적 negative 만 차단."""
    rule = BalanceDrainRule()
    tx = {
        "amount": 1_500_000,
        "oldbalanceOrg": 1_500_000,
        "newbalanceOrig": 0,
    }
    res = rule.evaluate(tx, profile=None)
    assert res is not None
    assert res.action == "BLOCK"


def test_classify_fraud_type_balance_drain():
    assert classify_fraud_type(["BALANCE_DRAIN"]) == "BALANCE_DRAIN"
    assert classify_fraud_type(["BALANCE_DRAIN", "AMOUNT_REVIEW"]) == "BALANCE_DRAIN"


def test_classify_graph_priority_over_balance_drain():
    """그래프 룰 동시 발동 시 MONEY_MULE 우선."""
    assert classify_fraud_type(["BALANCE_DRAIN", "MONEY_MULE_HUB"]) == "MONEY_MULE"
    assert classify_fraud_type(["BALANCE_DRAIN", "LAYERING_CHAIN"]) == "MONEY_MULE"
