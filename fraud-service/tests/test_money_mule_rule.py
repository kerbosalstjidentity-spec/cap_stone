"""W6.5-#3 — 머니뮬 hub-spoke 룰 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.graph_store import graph_store
from app.services.policy_merge import classify_fraud_type
from app.services.rule_engine import MoneyMuleRule


def _clean(*nodes: str) -> None:
    graph_store.clear(nodes=nodes)


def test_money_mule_rule_unit_fires():
    rule = MoneyMuleRule(min_fan_in=3, pass_through_ratio_threshold=0.8)
    tx = {"graph_features": {"sender_fan_in_count": 4, "sender_pass_through_ratio": 0.92}}
    res = rule.evaluate(tx, profile=None)
    assert res is not None
    assert res.action == "BLOCK"
    assert res.rule_id == "MONEY_MULE_HUB"


def test_money_mule_rule_unit_below_threshold():
    rule = MoneyMuleRule(min_fan_in=3, pass_through_ratio_threshold=0.8)
    # fan_in 충족하지만 pass_through 부족
    tx = {"graph_features": {"sender_fan_in_count": 5, "sender_pass_through_ratio": 0.5}}
    assert rule.evaluate(tx, profile=None) is None
    # pass_through 충족하지만 fan_in 부족
    tx = {"graph_features": {"sender_fan_in_count": 1, "sender_pass_through_ratio": 0.95}}
    assert rule.evaluate(tx, profile=None) is None


def test_money_mule_rule_no_graph_features():
    rule = MoneyMuleRule()
    assert rule.evaluate({}, profile=None) is None


def test_classify_fraud_type_money_mule_hub():
    assert classify_fraud_type(["MONEY_MULE_HUB"]) == "MONEY_MULE"
    # MONEY_MULE_HUB 가 BLACKLIST 다음 우선순위
    assert classify_fraud_type(["MONEY_MULE_HUB", "AMOUNT_REVIEW"]) == "MONEY_MULE"
    assert classify_fraud_type(["BLACKLIST", "MONEY_MULE_HUB"]) == "BLACKLIST"


def test_money_mule_e2e_via_evaluate():
    """그래프 store 시드 후 evaluate 호출 — MONEY_MULE_HUB 룰 발동."""
    client = TestClient(app)
    mule = "w653_mule_user"
    _clean(mule)
    try:
        # 4명에게서 1000씩 받음 (graph_store 직접 시드)
        for s in ["v1", "v2", "v3", "v4"]:
            graph_store.record(s, mule, 1000.0)
        # mule 이 받은 금액의 90% 를 다른 노드로 송금 (받자마자 통과)
        graph_store.record(mule, "exit_a", 980.0)
        graph_store.record(mule, "exit_b", 1000.0)
        graph_store.record(mule, "exit_c", 1620.0)
        # 이제 mule 이 또 다른 거래 — 룰 발동 기대
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W653-MULE", "score": 0.2, "amount": 50_000,
            "user_id": mule, "receiver_id": "exit_d",
        })
        assert r.status_code == 200
        data = r.json()
        rule_id = data.get("rule_id") or ""
        assert "MONEY_MULE_HUB" in rule_id, f"머니뮬 룰 미발동: {rule_id}"
        assert data["fraud_type"] == "MONEY_MULE"
        assert data["final_action"] == "BLOCK"
    finally:
        _clean(mule, "exit_a", "exit_b", "exit_c", "exit_d", "v1", "v2", "v3", "v4")


def test_normal_sender_no_mule_rule():
    """평범한 사용자 — 그래프 시그널 없음, 룰 미발동."""
    client = TestClient(app)
    user = "w653_normal_user"
    _clean(user)
    try:
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W653-N", "score": 0.1, "amount": 10_000,
            "user_id": user, "receiver_id": "merchant_x",
        })
        rule_id = r.json().get("rule_id") or ""
        assert "MONEY_MULE_HUB" not in rule_id
    finally:
        _clean(user)
