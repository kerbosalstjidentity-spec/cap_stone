from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_fraud_evaluate_pass():
    r = client.post("/v1/fraud/evaluate", json={"tx_id": "TX001", "score": 0.0, "amount": 10000})
    assert r.status_code == 200
    data = r.json()
    assert data["admin_routing"]["action"] == "PASS"
    assert data["user_message"]["status"] == "Secure"
    assert data["step_up_auth"]["push_sent"] is False


def test_fraud_evaluate_review():
    r = client.post("/v1/fraud/evaluate", json={"tx_id": "TX002", "score": 0.5, "amount": 10000})
    assert r.status_code == 200
    data = r.json()
    assert data["admin_routing"]["action"] == "REVIEW"
    # 모든 action에 user_message 반환
    assert data["user_message"]["status"] == "PendingVerification"
    # fcm_token 없이 호출 → 실제 발송 없음
    assert data["step_up_auth"]["push_sent"] is False


def test_risk_leakage_report_endpoint():
    r = client.get("/v1/fraud/risk-leakage-report", params={"total_processed_amount": 1000000})
    assert r.status_code == 200
    report = r.json()
    assert "report_date" in report
    assert "current_leakage_estimate" in report
    assert "insight" in report
