from app.services.fraud_service import FraudServiceManager, generate_risk_leakage_report, SYSTEM_CONFIG


def test_get_admin_routing_block():
    m = FraudServiceManager({"tx_id": "x", "score": SYSTEM_CONFIG["BLOCK_THRESHOLD"], "amount": 1000})
    assert m.get_admin_routing()["action"] == "BLOCK"


def test_get_admin_routing_review():
    m = FraudServiceManager({"tx_id": "x", "score": SYSTEM_CONFIG["REVIEW_THRESHOLD"], "amount": 1000})
    assert m.get_admin_routing()["action"] == "REVIEW"


def test_get_admin_routing_soft_review():
    m = FraudServiceManager({"tx_id": "x", "score": SYSTEM_CONFIG["P99_THRESHOLD"], "amount": 1000})
    assert m.get_admin_routing()["action"] == "SOFT_REVIEW"


def test_get_admin_routing_pass():
    m = FraudServiceManager({"tx_id": "x", "score": SYSTEM_CONFIG["P99_THRESHOLD"] - 1e-6, "amount": 1000})
    assert m.get_admin_routing()["action"] == "PASS"


def test_get_user_trust_message_on_pass():
    m = FraudServiceManager({"tx_id": "x", "score": 0.0, "amount": 1000})
    msg = m.get_user_trust_message()
    assert msg is not None
    assert "Secure" in msg["status"]


def test_get_user_trust_message_non_pass():
    # 모든 action에 메시지 반환 — REVIEW → PendingVerification
    m = FraudServiceManager({"tx_id": "x", "score": 0.5, "amount": 1000})
    msg = m.get_user_trust_message()
    assert msg is not None
    assert msg["status"] == "PendingVerification"


def test_trigger_step_up_auth_for_review():
    # fcm_token 없으면 push_sent=False, type은 STEP_UP_AUTH
    m = FraudServiceManager({"tx_id": "x", "score": 0.5, "amount": 1000})
    r = m.trigger_step_up_auth()
    assert r["type"] == "STEP_UP_AUTH"
    assert r["push_sent"] is False

    # fcm_token 있으면 push_sent=True
    m2 = FraudServiceManager({"tx_id": "x", "score": 0.5, "amount": 1000, "fcm_token": "dummy_token"})
    r2 = m2.trigger_step_up_auth()
    assert r2["push_sent"] is True


def test_trigger_step_up_auth_for_pass():
    m = FraudServiceManager({"tx_id": "x", "score": 0.0, "amount": 1000})
    r = m.trigger_step_up_auth()
    assert r["push_sent"] is False


def test_generate_risk_leakage_report_formula():
    total = 1000000
    report = generate_risk_leakage_report(total)
    expected = total * (1 - SYSTEM_CONFIG["PASS_RATE"]) * SYSTEM_CONFIG["MISS_RATE"]
    assert report["current_leakage_estimate"].startswith("₩")
    assert int(report["current_leakage_estimate"].replace("₩", "").replace(",", "")) == round(expected)
