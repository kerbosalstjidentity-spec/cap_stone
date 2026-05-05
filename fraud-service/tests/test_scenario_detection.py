"""W5.5-#1 — 시나리오 시뮬레이터 + 검출률 집계 라우터 테스트.

본 테스트는 합성기와 라우터의 형태/결정성/스모크 검출률을 검증한다.
시나리오별 ≥80% 강건 회귀 테스트는 W5.5-#7 에서 별도로 강화한다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.scenario_generator import (
    SCENARIO_TYPES,
    generate,
    generate_all,
)

client = TestClient(app)

REQUIRED_KEYS = {"tx_id", "score", "amount", "user_id", "hour", "is_foreign_ip"}


def test_scenario_generator_shapes():
    bundles = generate_all(count=50)
    assert set(bundles.keys()) == set(SCENARIO_TYPES)
    for name, txs in bundles.items():
        assert len(txs) == 50, f"{name} count mismatch"
        for tx in txs:
            missing = REQUIRED_KEYS - tx.keys()
            assert not missing, f"{name} tx missing keys: {missing}"
            assert 0.0 <= tx["score"] <= 1.0
            assert tx["amount"] >= 0


def test_seed_determinism():
    a = generate("VOICE_PHISHING", count=20, seed=7)
    b = generate("VOICE_PHISHING", count=20, seed=7)
    c = generate("VOICE_PHISHING", count=20, seed=8)
    assert a == b
    assert a != c


def test_unknown_scenario_raises():
    import pytest

    with pytest.raises(ValueError):
        generate("UNKNOWN_TYPE", count=1)


def test_route_returns_table():
    r = client.post("/v1/scenario/run", json={"count": 30, "seed": 42})
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data["results"].keys()) == set(SCENARIO_TYPES)
    for name, row in data["results"].items():
        assert row["total"] == 30
        assert {"BLOCK", "REVIEW", "SOFT_REVIEW", "PASS", "detection_rate"} <= row.keys()
        assert 0.0 <= row["detection_rate"] <= 1.0
    assert "overall_detection_rate" in data


def test_route_lists_types():
    r = client.get("/v1/scenario/types")
    assert r.status_code == 200
    assert set(r.json()["scenarios"]) == set(SCENARIO_TYPES)


def test_route_rejects_unknown_scenario():
    r = client.post(
        "/v1/scenario/run",
        json={"scenarios": ["VOICE_PHISHING", "UNKNOWN"], "count": 10},
    )
    assert r.status_code == 400


def test_voice_phishing_detection_smoke():
    """VOICE_PHISHING 은 score 0.7+ ∧ amount ≥5M 으로 합성 — 100% BLOCK 기대.

    W5.5-#7 강건 회귀에서 ≥80% 강한 floor + dominant fraud_type 라벨까지 검증.
    """
    r = client.post(
        "/v1/scenario/run",
        json={"scenarios": ["VOICE_PHISHING"], "count": 100, "seed": 42},
    )
    assert r.status_code == 200
    rate = r.json()["results"]["VOICE_PHISHING"]["detection_rate"]
    assert rate >= 0.8, f"VOICE_PHISHING detection_rate={rate} below floor 0.8"
