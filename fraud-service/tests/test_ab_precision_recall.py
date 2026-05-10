"""W7-#9 — variant 별 ground truth precision/recall 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.feedback_store import (
    feedback_store,
    precision_recall_by_variant,
)
from app.services.stats_collector import stats_collector

client = TestClient(app)


def setup_function(_):
    stats_collector.reset()
    feedback_store.clear()


def teardown_function(_):
    stats_collector.reset()
    feedback_store.clear()


def _record(tx, action, variant):
    stats_collector.record(
        tx, action, [], 0.5, 100.0,
        latency_ms=1.0, ab_variant=variant,
    )


def _cb(tx):
    feedback_store.record(tx_id=tx, user_id="u", amount=100.0)


def test_per_variant_precision_recall():
    # variant a: 4 evals — chargeback {T1,T2}, BLOCK {T1,T3}
    #   TP=1 (T1 fraud+detected), FN=1 (T2 fraud+pass), FP=1 (T3 detected+notfraud), TN=1 (T4)
    _record("T1", "BLOCK", "a")
    _record("T2", "PASS", "a")
    _record("T3", "BLOCK", "a")
    _record("T4", "PASS", "a")
    _cb("T1")
    _cb("T2")
    # variant b: 4 evals — chargeback {U1}, BLOCK {U1}
    #   TP=1, FN=0, FP=0, TN=3
    _record("U1", "BLOCK", "b")
    _record("U2", "PASS", "b")
    _record("U3", "PASS", "b")
    _record("U4", "PASS", "b")
    _cb("U1")

    with stats_collector._lock:
        entries = list(stats_collector._entries)
    out = precision_recall_by_variant(entries)
    a = out["by_variant"]["a"]
    b = out["by_variant"]["b"]
    assert a == {"tp": 1, "fn": 1, "fp": 1, "tn": 1,
                 "precision": 0.5, "recall": 0.5, "f1": 0.5, "n": 4}
    assert b["precision"] == 1.0
    assert b["recall"] == 1.0
    assert b["f1"] == 1.0
    assert out["chargeback_total"] == 3
    assert out["evaluated_total"] == 8


def test_unlabeled_bucket():
    _record("X1", "PASS", None)
    _record("X2", "BLOCK", None)
    _cb("X2")
    with stats_collector._lock:
        entries = list(stats_collector._entries)
    out = precision_recall_by_variant(entries)
    assert "unlabeled" in out["by_variant"]
    assert out["by_variant"]["unlabeled"]["tp"] == 1


def test_admin_endpoint():
    _record("E1", "BLOCK", "a")
    _cb("E1")
    r = client.get("/admin/api/ab-precision-recall")
    assert r.status_code == 200
    data = r.json()
    assert "a" in data["by_variant"]
    assert data["by_variant"]["a"]["tp"] == 1
    assert data["chargeback_total"] == 1
