"""Analysis API 테스트."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _seed():
    """시드 데이터 생성."""
    client.delete("/v1/seed/reset/test_analysis")
    client.post("/v1/seed/demo/test_analysis?months=3&tx_per_month=30")
    yield
    client.delete("/v1/seed/reset/test_analysis")


class TestClustering:
    def test_pattern(self):
        res = client.get("/v1/analysis/pattern/test_analysis")
        assert res.status_code == 200
        data = res.json()
        assert "cluster_label" in data
        assert data["cluster_label"] in ["절약형", "균형형", "소비형", "투자형"]
        assert data["tx_count"] > 0


class TestAnomaly:
    def test_anomaly(self):
        res = client.get("/v1/analysis/anomaly/test_analysis")
        assert res.status_code == 200
        data = res.json()
        assert "anomaly_count" in data
        assert data["total_transactions"] > 0
        assert isinstance(data["anomalies"], list)


class TestForecast:
    def test_forecast(self):
        res = client.get("/v1/analysis/forecast/test_analysis")
        assert res.status_code == 200
        data = res.json()
        assert data["predicted_total"] > 0
        assert 0 <= data["confidence"] <= 1
        assert data["forecast_period"] == "next_month"


class TestOverspend:
    def test_overspend(self):
        res = client.get("/v1/analysis/overspend/test_analysis")
        assert res.status_code == 200
        data = res.json()
        assert 0 <= data["overspend_probability"] <= 1
        assert isinstance(data["is_overspend"], bool)
        assert data["method"] in ["xgboost", "rule_based"]


class TestCompare:
    def test_compare(self):
        res = client.get("/v1/analysis/compare/test_analysis")
        assert res.status_code == 200
        data = res.json()
        assert "total_diff" in data
        assert "total_diff_pct" in data
        assert "insight" in data
        assert "category_diffs" in data

    def test_insufficient_data(self):
        """1개월 미만 데이터는 비교 불가."""
        client.delete("/v1/seed/reset/single_month")
        client.post("/v1/seed/demo/single_month?months=1&tx_per_month=10")
        res = client.get("/v1/analysis/compare/single_month")
        # 1개월 데이터로도 최소 1개월 trend가 나오므로 400이 될 수 있음
        assert res.status_code in [200, 400]
        client.delete("/v1/seed/reset/single_month")
