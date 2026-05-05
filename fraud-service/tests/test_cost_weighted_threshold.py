"""W6.5-#5 — 비용 가중 BLOCK 임계값 테스트."""
from __future__ import annotations

from app.services.fraud_service import SYSTEM_CONFIG, FraudServiceManager


def test_low_score_high_amount_triggers_cost_block():
    """0.5 score × 1억원 = 5천만원 expected_loss — COST_BLOCK_KRW(3M) 초과 → BLOCK."""
    m = FraudServiceManager({"score": 0.5, "amount": 100_000_000})
    assert m.get_expected_loss() == 50_000_000
    assert m.get_model_action() == "BLOCK"


def test_high_score_tiny_amount_falls_back_to_score_band():
    """0.99 × 1000 = 990 expected_loss < COST_REVIEW_KRW. 그래도 score 0.99 ≥ BLOCK_THRESHOLD → BLOCK."""
    m = FraudServiceManager({"score": 0.99, "amount": 1_000})
    # cost-band → PASS, score-band → BLOCK; max → BLOCK
    assert m.get_model_action() == "BLOCK"


def test_medium_score_medium_amount_review_via_cost():
    """0.4 × 2M = 800k expected_loss — COST_REVIEW_KRW(500k) 초과, COST_BLOCK 미만 → REVIEW.
    score 0.4 ≥ REVIEW_THRESHOLD 0.35 이라 자체로도 REVIEW. 결과 REVIEW."""
    m = FraudServiceManager({"score": 0.4, "amount": 2_000_000})
    assert m.get_model_action() == "REVIEW"


def test_low_score_low_amount_pass():
    """저위험 거래 — 어느 시그널도 임계 미달 → PASS. (score < P99_THRESHOLD=0.005)."""
    m = FraudServiceManager({"score": 0.001, "amount": 1_000})
    assert m.get_model_action() == "PASS"


def test_low_score_borderline_amount_review():
    """0.2 × 3M = 600k > COST_REVIEW_KRW(500k) → REVIEW (score-band 는 SOFT_REVIEW)."""
    m = FraudServiceManager({"score": 0.2, "amount": 3_000_000})
    assert m.get_expected_loss() == 600_000
    # cost-band REVIEW, score-band 0.2 ∈ [0.005, 0.35) → SOFT_REVIEW; max=REVIEW
    assert m.get_model_action() == "REVIEW"


def test_expected_loss_response_field():
    """evaluate 응답에 expected_loss 노출."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    r = client.post("/v1/fraud/evaluate", json={
        "tx_id": "W655-1", "score": 0.5, "amount": 1_000_000,
        "user_id": "w655_test_user",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["expected_loss"] == 500_000.0


def test_cost_thresholds_in_system_config():
    assert "COST_BLOCK_KRW" in SYSTEM_CONFIG
    assert "COST_REVIEW_KRW" in SYSTEM_CONFIG
    assert SYSTEM_CONFIG["COST_BLOCK_KRW"] >= SYSTEM_CONFIG["COST_REVIEW_KRW"]
