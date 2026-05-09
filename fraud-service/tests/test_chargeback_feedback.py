"""W7.5-#4 — chargeback 피드백 루프 + precision/recall 메트릭 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.feedback_store import feedback_store, precision_recall_summary
from app.services.stats_collector import StatEntry, stats_collector

client = TestClient(app)


def _reset():
    feedback_store.clear()
    stats_collector.reset()


def test_record_chargeback_endpoint():
    _reset()
    r = client.post(
        "/v1/fraud/feedback/chargeback",
        json={"tx_id": "TX-CB-1", "user_id": "u1", "amount": 1_000_000, "reason": "voice_phishing"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["tx_id"] == "TX-CB-1"
    assert body["label"] == "FRAUD"
    assert body["total_recorded"] == 1


def test_list_chargebacks():
    _reset()
    for i in range(3):
        client.post(
            "/v1/fraud/feedback/chargeback",
            json={"tx_id": f"TX-{i}", "user_id": "u", "amount": 100, "reason": "x"},
        )
    r = client.get("/v1/fraud/feedback/chargeback")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_precision_recall_perfect_detection():
    _reset()
    # 5건 사기, 모두 BLOCK 처리 → precision=1, recall=1
    for i in range(5):
        feedback_store.record(tx_id=f"FR-{i}", user_id="u", amount=100)
        stats_collector.record(f"FR-{i}", "BLOCK", ["R1"], score=0.9, amount=100)
    summary = precision_recall_summary(list(stats_collector._entries))
    assert summary["tp"] == 5
    assert summary["fn"] == 0
    assert summary["fp"] == 0
    assert summary["precision"] == 1.0
    assert summary["recall"] == 1.0


def test_precision_recall_with_misses():
    _reset()
    # 4건 사기 중 3건 BLOCK, 1건 PASS
    for i in range(4):
        feedback_store.record(tx_id=f"FR-{i}", user_id="u", amount=100)
    stats_collector.record("FR-0", "BLOCK", [], 0.9, 100)
    stats_collector.record("FR-1", "REVIEW", [], 0.7, 100)
    stats_collector.record("FR-2", "BLOCK", [], 0.9, 100)
    stats_collector.record("FR-3", "PASS", [], 0.2, 100)
    # 정상 거래 2건도 평가, 그 중 1건 잘못 BLOCK (FP)
    stats_collector.record("OK-1", "BLOCK", [], 0.5, 100)
    stats_collector.record("OK-2", "PASS", [], 0.1, 100)

    summary = precision_recall_summary(list(stats_collector._entries))
    assert summary["tp"] == 3
    assert summary["fn"] == 1
    assert summary["fp"] == 1
    assert summary["tn"] == 1
    assert summary["precision"] == 0.75  # 3 / (3+1)
    assert summary["recall"] == 0.75     # 3 / (3+1)


def test_metrics_endpoint():
    _reset()
    feedback_store.record(tx_id="MX-1", user_id="u", amount=100)
    stats_collector.record("MX-1", "BLOCK", [], 0.9, 100)
    r = client.get("/v1/fraud/feedback/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["tp"] == 1
    assert body["chargeback_total"] == 1
    assert body["precision"] == 1.0


def test_chargeback_overwrite_same_tx():
    _reset()
    feedback_store.record(tx_id="DUP", user_id="u1", amount=100, reason="r1")
    feedback_store.record(tx_id="DUP", user_id="u2", amount=200, reason="r2")
    assert feedback_store.count() == 1
    e = feedback_store.get("DUP")
    assert e is not None
    assert e.user_id == "u2"
    assert e.amount == 200.0
