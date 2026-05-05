"""W6.5-#6 — fraud_type 별 차등 임계값 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.graph_store import graph_store
from app.services.policy_merge import (
    FRAUD_TYPE_BLOCK_THRESHOLDS,
    apply_fraud_type_threshold,
)

client = TestClient(app)


def test_thresholds_dict_has_all_types():
    expected = {
        "BLACKLIST", "MONEY_MULE", "CARD_TESTING",
        "VOICE_PHISHING", "ACCOUNT_TAKEOVER",
        "AMOUNT_ANOMALY", "NORMAL",
    }
    assert expected <= FRAUD_TYPE_BLOCK_THRESHOLDS.keys()


def test_thresholds_strength_ordering():
    """룰 시그널 강한 유형의 임계가 더 낮아야 함."""
    t = FRAUD_TYPE_BLOCK_THRESHOLDS
    assert t["BLACKLIST"] <= t["MONEY_MULE"] <= t["VOICE_PHISHING"]
    assert t["MONEY_MULE"] <= t["CARD_TESTING"] <= t["AMOUNT_ANOMALY"]
    assert t["NORMAL"] > 1.0  # 절대 적용 안 됨


def test_apply_already_block_unchanged():
    assert apply_fraud_type_threshold("BLOCK", 0.1, "MONEY_MULE") == "BLOCK"


def test_apply_normal_type_unchanged():
    """NORMAL 유형이면 score 1.0 이라도 그대로."""
    assert apply_fraud_type_threshold("REVIEW", 1.0, "NORMAL") == "REVIEW"


def test_apply_money_mule_score_05_upgrades():
    """MONEY_MULE 임계 0.5 — score 0.5 면 REVIEW 가 BLOCK 으로."""
    assert apply_fraud_type_threshold("REVIEW", 0.5, "MONEY_MULE") == "BLOCK"
    # 0.49 는 미만 — 변화 없음
    assert apply_fraud_type_threshold("REVIEW", 0.49, "MONEY_MULE") == "REVIEW"


def test_apply_card_testing_higher_threshold():
    """CARD_TESTING 임계 0.7."""
    assert apply_fraud_type_threshold("REVIEW", 0.7, "CARD_TESTING") == "BLOCK"
    assert apply_fraud_type_threshold("REVIEW", 0.6, "CARD_TESTING") == "REVIEW"


def test_apply_amount_anomaly_conservative():
    """AMOUNT_ANOMALY 임계 0.85 — 금액만 보면 보수적."""
    assert apply_fraud_type_threshold("REVIEW", 0.84, "AMOUNT_ANOMALY") == "REVIEW"
    assert apply_fraud_type_threshold("REVIEW", 0.85, "AMOUNT_ANOMALY") == "BLOCK"


def test_apply_pass_can_upgrade():
    """PASS 액션도 임계 통과 시 BLOCK 으로 (룰이 발동했지만 cost/score 가 낮을 때)."""
    assert apply_fraud_type_threshold("PASS", 0.5, "MONEY_MULE") == "BLOCK"


def test_e2e_money_mule_low_score_blocked():
    """그래프 룰이 mule 발동 + score 0.5 → BLOCK 승격 (기존 score-only 라면 REVIEW)."""
    mule = "w656_mule"
    graph_store.clear(nodes=[mule, "exit_a", "exit_b", "exit_c", "v1", "v2", "v3", "v4"])
    try:
        # mule hub 시드
        for s in ["v1", "v2", "v3", "v4"]:
            graph_store.record(s, mule, 1000.0)
        graph_store.record(mule, "exit_a", 980.0)
        graph_store.record(mule, "exit_b", 1000.0)
        graph_store.record(mule, "exit_c", 1620.0)

        # score 0.5 — 기존엔 REVIEW band, mule 룰이 BLOCK 자체 발동
        # apply_fraud_type_threshold 까지 거치면 명백히 BLOCK
        r = client.post("/v1/fraud/evaluate", json={
            "tx_id": "W656-MULE", "score": 0.5, "amount": 100_000,
            "user_id": mule, "receiver_id": "exit_d",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["fraud_type"] == "MONEY_MULE"
        assert body["final_action"] == "BLOCK"
    finally:
        graph_store.clear(nodes=[mule, "exit_a", "exit_b", "exit_c", "exit_d", "v1", "v2", "v3", "v4"])
