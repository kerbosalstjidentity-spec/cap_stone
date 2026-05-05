"""W5.5-#8 — evaluate flow 가 profile_store 에 자동 ingest 하는지 검증.

기존엔 운영자가 별도로 /v1/profile/ingest 를 호출해야 velocity/avg_amount 가
누적 → VelocityRule 등 profile-의존 룰이 영구히 비활성이었음.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.profile_store import profile_store

client = TestClient(app)


def _clean(user_id: str) -> None:
    profile_store.delete(user_id)


def test_evaluate_ingests_profile():
    uid = "w558_evaluate_ingest_user"
    _clean(uid)
    try:
        # 5건 평가 — 모두 같은 사용자
        for i in range(5):
            r = client.post(
                "/v1/fraud/evaluate",
                json={"tx_id": f"W558-{i}", "score": 0.1, "amount": 5_000, "user_id": uid, "hour": 12},
            )
            assert r.status_code == 200
        prof = profile_store.get_profile(uid)
        assert prof is not None, "profile_store ingest 가 evaluate 에서 호출되지 않음"
        assert prof.tx_count == 5
        assert prof.velocity["1m"] == 5
    finally:
        _clean(uid)


def test_evaluate_velocity_rule_fires_after_ingest():
    """6건째 평가에서 VelocityRule(5m≥3) 발동 — 자동 ingest 가 동작했다는 강한 증거."""
    uid = "w558_velocity_rule_user"
    _clean(uid)
    try:
        last = None
        for i in range(7):
            r = client.post(
                "/v1/fraud/evaluate",
                json={"tx_id": f"W558V-{i}", "score": 0.2, "amount": 50_000, "user_id": uid, "hour": 12},
            )
            assert r.status_code == 200
            last = r.json()
        # 마지막 평가에서 VELOCITY_FREQ 가 발동했어야 함
        rule_id = last.get("rule_id") or ""
        assert "VELOCITY_FREQ" in rule_id, f"velocity 룰이 발동하지 않음: {rule_id}"
    finally:
        _clean(uid)


def test_evaluate_no_user_id_does_not_crash():
    """user_id 없는 익명 거래는 ingest 스킵."""
    r = client.post(
        "/v1/fraud/evaluate",
        json={"tx_id": "W558-ANON", "score": 0.1, "amount": 1_000, "user_id": ""},
    )
    assert r.status_code == 200
