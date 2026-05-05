"""W6.5-#4 — LayeringRule (다단계 자금세탁 체인) 테스트."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.graph_store import graph_store
from app.services.policy_merge import classify_fraud_type
from app.services.rule_engine import LayeringRule


def _clean(*nodes: str) -> None:
    graph_store.clear(nodes=nodes)


def test_layering_unit_fires_chain():
    rule = LayeringRule(ratio_threshold=0.9, recent_inbound_threshold_min=10.0, hub_fan_in_threshold=3)
    tx = {"graph_features": {
        "sender_pass_through_ratio": 0.95,
        "sender_recent_inbound_min_ago": 3.0,  # 3분 전 받음
        "sender_fan_in_count": 1,  # 체인 — hub 아님
    }}
    res = rule.evaluate(tx, profile=None)
    assert res is not None
    assert res.action == "REVIEW"
    assert res.rule_id == "LAYERING_CHAIN"


def test_layering_skips_when_hub_pattern():
    """fan_in 이 hub 임계 이상이면 머니뮬 룰 영역 — Layering 미발동."""
    rule = LayeringRule(ratio_threshold=0.9, hub_fan_in_threshold=3)
    tx = {"graph_features": {
        "sender_pass_through_ratio": 0.95,
        "sender_recent_inbound_min_ago": 3.0,
        "sender_fan_in_count": 5,  # hub
    }}
    assert rule.evaluate(tx, profile=None) is None


def test_layering_skips_when_inbound_too_old():
    rule = LayeringRule(recent_inbound_threshold_min=10.0)
    tx = {"graph_features": {
        "sender_pass_through_ratio": 0.95,
        "sender_recent_inbound_min_ago": 30.0,  # 30분 전 — too old
        "sender_fan_in_count": 1,
    }}
    assert rule.evaluate(tx, profile=None) is None


def test_layering_skips_when_low_pass_through():
    rule = LayeringRule(ratio_threshold=0.9)
    tx = {"graph_features": {
        "sender_pass_through_ratio": 0.5,  # half kept, not pass-through
        "sender_recent_inbound_min_ago": 3.0,
        "sender_fan_in_count": 1,
    }}
    assert rule.evaluate(tx, profile=None) is None


def test_layering_no_graph_features():
    assert LayeringRule().evaluate({}, profile=None) is None


def test_classify_fraud_type_layering():
    assert classify_fraud_type(["LAYERING_CHAIN"]) == "MONEY_MULE"
    assert classify_fraud_type(["LAYERING_CHAIN", "AMOUNT_REVIEW"]) == "MONEY_MULE"


def test_layering_e2e_via_evaluate():
    """A→B→C 체인 시뮬: B 가 A 에게서 받은 직후 C 로 ~95% 송금."""
    client = TestClient(app)
    a, b, c = "w654_alice", "w654_bob_chain", "w654_carol"
    _clean(a, b, c)
    try:
        # B 가 1분 전 A 에게서 1000을 받음
        graph_store.record(a, b, 1000.0, ts=time.time() - 60)
        # B 가 즉시 C 로 950 송금 — pass_through_ratio = 950/1000 = 0.95
        graph_store.record(b, c, 950.0, ts=time.time() - 30)
        # 이제 B 가 또 다른 거래 — LayeringRule 발동
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W654-CHAIN", "score": 0.2, "amount": 50_000,
            "user_id": b, "receiver_id": "w654_dave",
        })
        assert r.status_code == 200
        rule_id = r.json().get("rule_id") or ""
        assert "LAYERING_CHAIN" in rule_id, f"Layering 룰 미발동: {rule_id}"
        assert r.json()["fraud_type"] == "MONEY_MULE"
    finally:
        _clean(a, b, c, "w654_dave")
