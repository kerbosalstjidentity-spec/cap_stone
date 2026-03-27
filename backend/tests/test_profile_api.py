"""Profile API 테스트."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    """각 테스트 전 사용자 데이터 초기화."""
    client.delete("/v1/profile/test_user")
    yield
    client.delete("/v1/profile/test_user")


def _ingest(user_id: str = "test_user", amount: float = 25000, category: str = "food") -> dict:
    return client.post("/v1/profile/ingest", json={
        "transaction_id": f"tx_{amount}",
        "user_id": user_id,
        "amount": amount,
        "timestamp": "2026-03-27T12:00:00+00:00",
        "merchant_id": "test_merchant",
        "category": category,
        "channel": "app",
        "is_domestic": True,
        "memo": "테스트",
    }).json()


class TestIngest:
    def test_single(self):
        res = _ingest()
        assert res["status"] == "ingested"
        assert res["transaction_id"] == "tx_25000"

    def test_batch(self):
        res = client.post("/v1/profile/ingest/batch", json={
            "transactions": [
                {"transaction_id": "b1", "user_id": "test_user", "amount": 10000,
                 "timestamp": "2026-03-27T10:00:00+00:00", "merchant_id": "m1",
                 "category": "food"},
                {"transaction_id": "b2", "user_id": "test_user", "amount": 20000,
                 "timestamp": "2026-03-27T11:00:00+00:00", "merchant_id": "m2",
                 "category": "shopping"},
            ]
        })
        assert res.json()["count"] == 2


class TestProfile:
    def test_get(self):
        _ingest(amount=10000, category="food")
        _ingest(amount=20000, category="shopping")
        res = client.get("/v1/profile/test_user")
        assert res.status_code == 200
        data = res.json()
        assert data["total_tx_count"] == 2
        assert data["total_amount"] == 30000

    def test_not_found(self):
        res = client.get("/v1/profile/nonexistent")
        assert res.status_code == 404

    def test_categories(self):
        _ingest(amount=15000, category="food")
        res = client.get("/v1/profile/test_user/categories")
        assert res.status_code == 200
        cats = res.json()["categories"]
        assert len(cats) >= 1
        assert cats[0]["category"] == "food"

    def test_delete(self):
        _ingest()
        res = client.delete("/v1/profile/test_user")
        assert res.json()["status"] == "deleted"
        assert client.get("/v1/profile/test_user").status_code == 404
