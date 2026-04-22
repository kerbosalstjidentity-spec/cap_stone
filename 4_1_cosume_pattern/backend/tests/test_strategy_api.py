"""Strategy API 테스트."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _seed():
    client.delete("/v1/seed/reset/test_strat")
    client.post("/v1/seed/demo/test_strat?months=3&tx_per_month=30")
    yield
    client.delete("/v1/seed/reset/test_strat")


class TestRecommend:
    def test_recommend(self):
        res = client.get("/v1/strategy/recommend/test_strat")
        assert res.status_code == 200
        data = res.json()
        assert "cluster_label" in data
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) >= 1
        assert 0 <= data["risk_score"] <= 1

    def test_saving_opportunities(self):
        res = client.get("/v1/strategy/recommend/test_strat")
        data = res.json()
        for s in data.get("saving_opportunities", []):
            assert "category" in s
            assert "potential_saving" in s
            assert s["potential_saving"] > 0


class TestBudget:
    def test_set_and_get(self):
        budget = {
            "user_id": "test_strat",
            "monthly_total": 1500000,
            "items": [
                {"category": "food", "budget_amount": 400000},
                {"category": "shopping", "budget_amount": 300000},
                {"category": "transport", "budget_amount": 100000},
            ]
        }
        res = client.post("/v1/strategy/budget/test_strat", json=budget)
        assert res.json()["status"] == "budget_set"

        res = client.get("/v1/strategy/budget/test_strat")
        assert res.status_code == 200
        assert res.json()["budget"]["monthly_total"] == 1500000

    def test_not_found(self):
        res = client.get("/v1/strategy/budget/nonexistent")
        assert res.status_code == 404


class TestSavings:
    def test_savings_with_budget(self):
        # 매우 낮은 예산을 설정하여 초과가 발생하도록
        budget = {
            "user_id": "test_strat",
            "monthly_total": 100000,
            "items": [
                {"category": "food", "budget_amount": 10000},
            ]
        }
        client.post("/v1/strategy/budget/test_strat", json=budget)
        res = client.get("/v1/strategy/savings/test_strat")
        assert res.status_code == 200
        # 데모 데이터에서 식비가 10,000원을 초과할 가능성이 매우 높음
        data = res.json()
        assert isinstance(data["savings"], list)


class TestSeed:
    def test_seed_and_reset(self):
        res = client.post("/v1/seed/demo/seed_test?months=2&tx_per_month=20")
        assert res.json()["status"] == "seeded"
        assert res.json()["transactions_created"] > 0

        res = client.delete("/v1/seed/reset/seed_test")
        assert res.json()["status"] == "reset"
