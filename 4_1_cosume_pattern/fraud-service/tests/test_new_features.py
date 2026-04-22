"""D-2 배치 / C-4 Rate Limit / D-4 디바이스 핑거프린팅 / D-3 A/B 테스트."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.device_store import DeviceStore

client = TestClient(app)


# ── D-2 배치 평가 ─────────────────────────────────────────────────────────────

def test_batch_evaluate_basic():
    payload = {
        "transactions": [
            {"tx_id": "b1", "score": 0.0, "amount": 5_000},
            {"tx_id": "b2", "score": 0.95, "amount": 6_000_000},
            {"tx_id": "b3", "score": 0.5, "amount": 50_000},
        ]
    }
    r = client.post("/v1/fraud/evaluate/batch", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert "action_summary" in data
    ids = [row["tx_id"] for row in data["results"]]
    assert ids == ["b1", "b2", "b3"]


def test_batch_evaluate_block_detected():
    payload = {
        "transactions": [
            {"tx_id": "big1", "score": 0.95, "amount": 9_000_000},
        ]
    }
    r = client.post("/v1/fraud/evaluate/batch", json=payload)
    assert r.json()["results"][0]["final_action"] == "BLOCK"


def test_batch_empty_rejected():
    r = client.post("/v1/fraud/evaluate/batch", json={"transactions": []})
    assert r.status_code == 422


def test_batch_over_limit_rejected():
    txs = [{"tx_id": f"t{i}", "score": 0.1, "amount": 1000} for i in range(501)]
    r = client.post("/v1/fraud/evaluate/batch", json={"transactions": txs})
    assert r.status_code == 422


# ── C-4 Rate Limiting ─────────────────────────────────────────────────────────

def test_rate_limit_under_limit():
    """RPM 이내 요청은 200."""
    r = client.post("/v1/fraud/evaluate", json={"tx_id": "rl1", "score": 0.1, "amount": 1000})
    assert r.status_code == 200


def test_rate_limit_429_when_exceeded(monkeypatch):
    """윈도우를 강제로 꽉 채운 후 429 확인."""
    import app.middleware.rate_limit as rl
    monkeypatch.setattr(rl, "_RPM", 2)
    # 기존 카운터 초기화
    with rl._lock:
        rl._windows.clear()

    r1 = client.post("/v1/fraud/evaluate", json={"tx_id": "rl_a", "score": 0.1, "amount": 1000})
    r2 = client.post("/v1/fraud/evaluate", json={"tx_id": "rl_b", "score": 0.1, "amount": 1000})
    r3 = client.post("/v1/fraud/evaluate", json={"tx_id": "rl_c", "score": 0.1, "amount": 1000})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers

    # 원복
    monkeypatch.setattr(rl, "_RPM", 120)
    with rl._lock:
        rl._windows.clear()


# ── D-4 디바이스 핑거프린팅 ───────────────────────────────────────────────────

def test_device_fingerprint_single_user():
    store = DeviceStore()
    store.record("dev1", "user_a")
    users = store.unique_users_in_window("dev1", 60)
    assert users == {"user_a"}


def test_device_fingerprint_multi_user():
    store = DeviceStore()
    store.record("dev2", "user_a")
    store.record("dev2", "user_b")
    users = store.unique_users_in_window("dev2", 60)
    assert len(users) == 2


def test_device_fingerprint_rule_fires_via_api():
    # 같은 device_id로 두 사용자 연속 거래
    client.post("/v1/fraud/evaluate", json={
        "tx_id": "df1", "score": 0.1, "amount": 1000,
        "device_id": "shared_device_xyz", "user_id": "user_alpha",
    })
    r = client.post("/v1/fraud/evaluate", json={
        "tx_id": "df2", "score": 0.1, "amount": 1000,
        "device_id": "shared_device_xyz", "user_id": "user_beta",
    })
    data = r.json()
    # DEVICE_FINGERPRINT 룰 발동 확인
    assert data["rule_id"] is not None
    assert "DEVICE_FINGERPRINT" in (data["rule_id"] or "")


# ── D-3 A/B 통계 엔드포인트 ──────────────────────────────────────────────────

def test_ab_stats_endpoint():
    r = client.get("/admin/api/ab-stats")
    assert r.status_code == 200
    assert "ab_stats" in r.json()


def test_ab_stats_reset():
    r = client.delete("/admin/api/ab-stats")
    assert r.status_code == 200
    assert r.json()["reset"] is True


# ── Audit log 엔드포인트 ──────────────────────────────────────────────────────

def test_audit_log_endpoint():
    # 평가 한 건 먼저
    client.post("/v1/fraud/evaluate", json={"tx_id": "audit_chk", "score": 0.1, "amount": 5000})
    r = client.get("/admin/api/audit?n=10")
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert isinstance(logs, list)
