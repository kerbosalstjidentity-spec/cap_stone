"""W5.5-#5 — fraud_type 다중분류 라벨 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.policy_merge import (
    FRAUD_TYPES,
    classify_fraud_type,
    fraud_type_label_ko,
)

client = TestClient(app)


def test_classify_normal_when_no_rules():
    assert classify_fraud_type([]) == "NORMAL"
    assert classify_fraud_type("") == "NORMAL"
    assert classify_fraud_type(None) == "NORMAL"


def test_classify_blacklist_takes_precedence():
    assert classify_fraud_type(["BLACKLIST", "AMOUNT_BLOCK"]) == "BLACKLIST"


def test_classify_card_testing_split():
    assert classify_fraud_type(["SPLIT_TXN"]) == "CARD_TESTING"
    assert classify_fraud_type("SPLIT_TXN,VELOCITY_FREQ") == "CARD_TESTING"


def test_classify_card_testing_velocity_only():
    # 소액 다건 = velocity 만 발동 (금액 룰 없음)
    assert classify_fraud_type(["VELOCITY_FREQ"]) == "CARD_TESTING"


def test_classify_account_takeover_foreign():
    assert classify_fraud_type(["FOREIGN_IP", "AMOUNT_REVIEW"]) == "ACCOUNT_TAKEOVER"
    assert classify_fraud_type(["DEVICE_FINGERPRINT"]) == "ACCOUNT_TAKEOVER"


def test_classify_money_mule_velocity_plus_amount():
    assert classify_fraud_type(["VELOCITY_FREQ", "AMOUNT_REVIEW"]) == "MONEY_MULE"


def test_classify_voice_phishing_time_plus_amount():
    assert classify_fraud_type(["TIME_RISK", "AMOUNT_BLOCK"]) == "VOICE_PHISHING"


def test_classify_amount_anomaly_only_amount():
    assert classify_fraud_type(["AMOUNT_BLOCK"]) == "AMOUNT_ANOMALY"
    assert classify_fraud_type(["AMOUNT_SPIKE", "NEW_MERCHANT"]) == "AMOUNT_ANOMALY"


def test_label_ko_round_trip():
    for ft in FRAUD_TYPES:
        label = fraud_type_label_ko(ft)
        assert isinstance(label, str) and label
    assert fraud_type_label_ko("UNKNOWN_KEY") == "UNKNOWN_KEY"  # fallback


def test_evaluate_response_has_fraud_type():
    """`/v1/fraud/evaluate` 응답에 fraud_type 필드 포함되는지."""
    payload = {
        "tx_id": "TST-FT-1",
        "score": 0.6,
        "amount": 6_000_000,  # AMOUNT_BLOCK 룰 발동
        "user_id": "user-fraud-type-test",
    }
    r = client.post("/v1/fraud/evaluate", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "fraud_type" in data
    assert "fraud_type_label" in data
    assert data["fraud_type"] in FRAUD_TYPES


def test_evaluate_voice_phishing_pattern():
    """야간 + 고액 → VOICE_PHISHING 라벨."""
    payload = {
        "tx_id": "TST-VP-1",
        "score": 0.7,
        "amount": 8_000_000,
        "hour": 3,
        "user_id": "user-vp-test",
    }
    r = client.post("/v1/fraud/evaluate", json=payload)
    assert r.status_code == 200
    data = r.json()
    # AMOUNT_BLOCK + TIME_RISK 둘 다 발동 → VOICE_PHISHING
    assert data["fraud_type"] == "VOICE_PHISHING"


def test_evaluate_normal_low_amount():
    payload = {
        "tx_id": "TST-N-1",
        "score": 0.0,
        "amount": 1_000,
        "user_id": "user-normal-test",
    }
    r = client.post("/v1/fraud/evaluate", json=payload)
    assert r.status_code == 200
    assert r.json()["fraud_type"] == "NORMAL"
