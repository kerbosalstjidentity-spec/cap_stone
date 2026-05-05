"""W6.5-#2 — 그래프 피처 추출기 테스트."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import graph_features as gf
from app.services.graph_store import graph_store


def _clean(*nodes: str) -> None:
    graph_store.clear(nodes=nodes)


def test_first_seen_unknown_receiver():
    receiver = "w652_first_seen_unknown"
    _clean(receiver)
    assert gf.dest_first_seen_within_24h(receiver) == 1


def test_first_seen_recent():
    receiver = "w652_first_seen_recent"
    _clean(receiver)
    graph_store.record("alice", receiver, 100.0, ts=time.time() - 3600)  # 1시간 전
    assert gf.dest_first_seen_within_24h(receiver) == 1
    _clean(receiver)


def test_first_seen_old_returns_zero():
    receiver = "w652_first_seen_old"
    _clean(receiver)
    # 25시간 전 — 24h 윈도우 밖이므로 first-seen=0 (자주 보인 수취인)
    graph_store.record("alice", receiver, 100.0, ts=time.time() - 25 * 3600)
    assert gf.dest_first_seen_within_24h(receiver) == 0
    _clean(receiver)


def test_inbound_velocity_1h():
    receiver = "w652_velocity_1h"
    _clean(receiver)
    now = time.time()
    for i in range(5):
        graph_store.record(f"sender_{i}", receiver, 100.0, ts=now - 60 * i)
    # 5건 모두 1h 내 → 5
    assert gf.dest_inbound_velocity_1h(receiver) == 5
    # 1건 1h+ 밖
    graph_store.record("old_sender", receiver, 100.0, ts=now - 3700)
    assert gf.dest_inbound_velocity_1h(receiver) == 5
    _clean(receiver)


def test_pass_through_ratio_money_mule():
    """받자마자 그대로 내보내는 hub 노드."""
    mule = "w652_pass_mule"
    _clean(mule)
    # 3명에게서 1000씩 받음
    for s in ["v1", "v2", "v3"]:
        graph_store.record(s, mule, 1000.0)
    # 980을 다른 노드로 송금
    graph_store.record(mule, "exit_a", 980.0)
    graph_store.record(mule, "exit_b", 1000.0)
    graph_store.record(mule, "exit_c", 990.0)

    ratio = gf.pass_through_ratio(mule)
    # 980+1000+990 = 2970 / 3000 = 0.99
    assert 0.95 <= ratio <= 1.0
    _clean(mule)


def test_pass_through_ratio_no_inbound():
    sender = "w652_no_inbound_sender"
    _clean(sender)
    graph_store.record(sender, "anyone", 100.0)
    assert gf.pass_through_ratio(sender) == 0.0  # inbound 없음 → 정의 불가, 0
    _clean(sender)


def test_extract_all_keys():
    feats = gf.extract_all({"user_id": "u1", "nameDest": "r1"})
    expected_keys = {
        "sender", "receiver",
        "dest_first_seen_within_24h", "dest_inbound_velocity_1h",
        "fan_in_count", "pass_through_ratio",
        "inbound_amount", "sender_outbound_amount",
    }
    assert expected_keys <= feats.keys()
    assert feats["sender"] == "u1"
    assert feats["receiver"] == "r1"


def test_extract_all_empty_safe():
    """빈 sender/receiver — 안전 디폴트."""
    feats = gf.extract_all({})
    assert feats["sender"] == ""
    assert feats["receiver"] == ""
    assert feats["fan_in_count"] == 0
    assert feats["pass_through_ratio"] == 0.0


def test_evaluate_response_includes_graph_features():
    """e2e — /v1/fraud/evaluate 응답에 graph_features 노출."""
    client = TestClient(app)
    sender = "w652_eval_sender"
    receiver = "w652_eval_receiver"
    _clean(sender, receiver)
    try:
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W652-1", "score": 0.1, "amount": 1000,
            "user_id": sender, "receiver_id": receiver,
        })
        assert r.status_code == 200
        body = r.json()
        assert "graph_features" in body
        feats = body["graph_features"]
        # 첫 거래 — receiver 가 first_seen=1
        assert feats["dest_first_seen_within_24h"] == 1
        assert feats["fan_in_count"] == 0  # 적재는 응답 후이므로 평가 시점엔 0
        # 두 번째 거래 — fan_in_count 가 1 로 증가했어야 함
        r2 = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W652-2", "score": 0.1, "amount": 1500,
            "user_id": "another_sender_w652", "receiver_id": receiver,
        })
        feats2 = r2.json()["graph_features"]
        assert feats2["fan_in_count"] >= 1
    finally:
        _clean(sender, receiver, "another_sender_w652")
