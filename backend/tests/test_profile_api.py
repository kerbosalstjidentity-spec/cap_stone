"""Profile API 테스트."""

import pytest
from fastapi.testclient import TestClient


def _ingest(client: TestClient, user_id: str = "test_user", amount: float = 25000, category: str = "food") -> dict:
    return client.post("/v1/profile/ingest", json={
        "transaction_id": f"tx_{user_id}_{amount}_{category}",
        "user_id": user_id,
        "amount": amount,
        "timestamp": "2026-03-01T12:00:00+00:00",
        "merchant_id": "test_merchant",
        "category": category,
        "channel": "app",
        "is_domestic": True,
        "memo": "테스트",
    }).json()


@pytest.fixture(autouse=True)
def _reset(api_client: TestClient):
    """각 테스트 전후 사용자 데이터 초기화."""
    api_client.delete("/v1/profile/test_user_profile")
    yield
    api_client.delete("/v1/profile/test_user_profile")


class TestIngest:
    def test_single(self, api_client: TestClient):
        res = _ingest(api_client, user_id="test_user_profile", amount=25000, category="food")
        assert res["status"] == "ingested"
        assert "test_user_profile" in res["transaction_id"]

    def test_batch(self, api_client: TestClient):
        res = api_client.post("/v1/profile/ingest/batch", json={
            "transactions": [
                {"transaction_id": "profile_b1", "user_id": "test_user_profile", "amount": 10000,
                 "timestamp": "2026-03-01T10:00:00+00:00", "merchant_id": "m1",
                 "category": "food"},
                {"transaction_id": "profile_b2", "user_id": "test_user_profile", "amount": 20000,
                 "timestamp": "2026-03-01T11:00:00+00:00", "merchant_id": "m2",
                 "category": "shopping"},
            ]
        })
        assert res.json()["count"] == 2


class TestProfile:
    def test_get(self, api_client: TestClient):
        _ingest(api_client, user_id="test_user_profile", amount=10000, category="food")
        _ingest(api_client, user_id="test_user_profile", amount=20000, category="shopping")
        res = api_client.get("/v1/profile/test_user_profile")
        assert res.status_code == 200
        data = res.json()
        assert data["total_tx_count"] == 2
        assert data["total_amount"] == 30000

    def test_not_found(self, api_client: TestClient):
        res = api_client.get("/v1/profile/nonexistent_user_xyz")
        assert res.status_code == 404

    def test_categories(self, api_client: TestClient):
        _ingest(api_client, user_id="test_user_profile", amount=15000, category="food")
        res = api_client.get("/v1/profile/test_user_profile/categories")
        assert res.status_code == 200
        cats = res.json()["categories"]
        assert len(cats) >= 1
        assert cats[0]["category"] == "food"

    def test_delete(self, api_client: TestClient):
        _ingest(api_client, user_id="test_user_profile")
        res = api_client.delete("/v1/profile/test_user_profile")
        assert res.json()["status"] == "deleted"
        assert api_client.get("/v1/profile/test_user_profile").status_code == 404
