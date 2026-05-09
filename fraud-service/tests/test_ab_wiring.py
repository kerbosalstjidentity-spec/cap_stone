"""W7-#6: shadow_evaluate ↔ _evaluate_one wiring + _record."""
from __future__ import annotations

from app.scoring import ab_test


def test_record_called_via_evaluate_one(monkeypatch):
    ab_test.reset_stats()
    from app.api import routes_fraud

    tx = {
        "tx_id": "T1", "user_id": "u1", "score": 0.1, "amount": 1000.0,
        "ab_variant": "b",
    }
    out = routes_fraud._evaluate_one(tx)
    stats = ab_test.get_stats()
    assert "b" in stats
    assert stats["b"]["count"] == 1
    assert stats["b"]["count"] == 1


def test_default_variant_a_when_omitted():
    ab_test.reset_stats()
    from app.api import routes_fraud
    routes_fraud._evaluate_one({"tx_id": "T2", "user_id": "u1", "score": 0.05, "amount": 100.0})
    stats = ab_test.get_stats()
    assert stats["a"]["count"] == 1


def test_shadow_evaluate_returns_score_a_only_when_no_b():
    out = ab_test.shadow_evaluate("T3", [[0.1]], {"model": None}, None)
    assert out["score_b"] is None
    assert out["serving"] == "a"


def test_load_bundle_b_disabled_when_path_empty(monkeypatch):
    monkeypatch.setattr(ab_test, "_MODEL_B_PATH", "")
    assert ab_test.load_bundle_b() is None
