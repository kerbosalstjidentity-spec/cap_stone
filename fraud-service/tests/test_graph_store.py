"""W6.5-#1 — 송금 그래프 store 테스트.

Redis 미가용 환경에서 in-memory 폴백 동작을 기준으로 검증.
Redis 통합은 docker-compose 환경에서 별도 검증.
"""
from __future__ import annotations

import time

import pytest

from app.services.graph_store import GraphStore, graph_store


@pytest.fixture
def gs():
    s = GraphStore()
    yield s


def test_record_and_inbound_outbound(gs):
    gs.record("alice", "bob", 1000.0, tx_id="t1")
    gs.record("alice", "bob", 500.0, tx_id="t2")
    gs.record("carol", "bob", 2000.0, tx_id="t3")

    bob_in = gs.inbound("bob")
    assert len(bob_in) == 3
    assert {e.sender for e in bob_in} == {"alice", "carol"}
    assert sum(e.amount for e in bob_in) == 3500.0

    alice_out = gs.outbound("alice")
    assert len(alice_out) == 2
    assert {e.receiver for e in alice_out} == {"bob"}


def test_fan_in_count(gs):
    for sender in ["a1", "a2", "a3", "a4"]:
        gs.record(sender, "mule", 100.0)
    # 같은 sender 가 다시 보내도 fan_in 은 distinct count
    gs.record("a1", "mule", 200.0)
    assert gs.fan_in_count("mule") == 4


def test_pass_through_amounts(gs):
    """머니뮬 의심 — receiver 가 받자마자 같은 금액 outbound."""
    gs.record("victim", "mule", 1000.0, tx_id="in")
    gs.record("mule", "exit", 980.0, tx_id="out")
    inbound_amt = gs.inbound_amount("mule")
    outbound_amt = gs.outbound_amount("mule")
    pass_through_ratio = outbound_amt / inbound_amt if inbound_amt else 0
    assert inbound_amt == 1000.0
    assert outbound_amt == 980.0
    assert pass_through_ratio >= 0.95  # hub-spoke 패턴 시그널


def test_window_filtering(gs):
    now = time.time()
    gs.record("old", "bob", 1.0, ts=now - 7200)  # 2시간 전
    gs.record("recent", "bob", 1.0, ts=now - 60)  # 1분 전
    # 5분 윈도우: recent 만
    edges_5m = gs.inbound("bob", window_minutes=5)
    assert len(edges_5m) == 1 and edges_5m[0].sender == "recent"
    # 3시간 윈도우: 둘 다
    edges_3h = gs.inbound("bob", window_minutes=180)
    assert len(edges_3h) == 2


def test_first_seen_ts(gs):
    now = time.time()
    gs.record("a", "newbob", 1.0, ts=now - 30)
    gs.record("b", "newbob", 1.0, ts=now - 10)
    fs = gs.first_seen_ts("newbob")
    assert fs is not None
    assert abs(fs - (now - 30)) < 0.1


def test_empty_inputs(gs):
    gs.record("", "bob", 1.0)  # ignored
    gs.record("alice", "", 1.0)  # ignored
    assert gs.inbound("bob") == []
    assert gs.outbound("alice") == []


def test_clear(gs):
    gs.record("alice", "bob", 1.0)
    gs.clear(nodes=["alice", "bob"])
    assert gs.inbound("bob") == []
    assert gs.outbound("alice") == []


def test_evaluate_records_graph_edge():
    """/v1/fraud/evaluate 호출 시 graph_store 가 자동 적재되는지 e2e."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.graph_store import graph_store as gs_singleton

    client = TestClient(app)
    sender = "w651_eval_user"
    receiver = "C12345_w651"
    gs_singleton.clear(nodes=[sender, receiver])
    try:
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W651-1", "score": 0.1, "amount": 5000,
            "user_id": sender, "merchant_id": "", "ip": "",
        })
        assert r.status_code == 200
        # nameDest 가 없으면 graph 적재 안 됨 — 빈 receiver
        assert gs_singleton.inbound(receiver) == []

        # PaySim 키(nameDest) 또는 receiver_id 포함 시 적재
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W651-2", "score": 0.1, "amount": 7500,
            "user_id": sender, "merchant_id": receiver,  # 아무 필드도 없음
        })
        # receiver_id/nameDest 어느 것도 없으니 여전히 0
        assert gs_singleton.inbound(receiver) == []

        # 정상 케이스: receiver_id 명시
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W651-3", "score": 0.1, "amount": 10_000,
            "user_id": sender, "receiver_id": receiver,
        })
        assert r.status_code == 200
        edges = gs_singleton.inbound(receiver)
        assert len(edges) == 1
        assert edges[0].sender == sender
        assert edges[0].amount == 10_000.0
    finally:
        gs_singleton.clear(nodes=[sender, receiver])
