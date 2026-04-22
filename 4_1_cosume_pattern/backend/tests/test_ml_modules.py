"""ML 모듈 단위 테스트."""

import numpy as np

from app.ml.anomaly import SpendAnomalyDetector
from app.ml.classifier import OverspendClassifier
from app.ml.clustering import SpendClusterModel
from app.ml.forecasting import SpendForecaster


class TestKMeans:
    def test_predict_unfitted(self):
        """미학습 상태에서 규칙 기반 fallback."""
        model = SpendClusterModel()
        result = model.predict({"food": 0.4, "shopping": 0.3, "transport": 0.1})
        assert "cluster_label" in result
        assert result["cluster_id"] == -1
        assert result["cluster_label"] in ["절약형", "균형형", "소비형"]

    def test_fit_and_predict(self):
        model = SpendClusterModel(n_clusters=3)
        profiles = [
            {"food": 0.6, "shopping": 0.1},
            {"food": 0.1, "shopping": 0.6},
            {"food": 0.3, "shopping": 0.3},
            {"food": 0.7, "shopping": 0.05},
            {"food": 0.05, "shopping": 0.7},
            {"food": 0.35, "shopping": 0.35},
        ]
        model.fit(profiles)
        assert model.is_fitted
        result = model.predict({"food": 0.5, "shopping": 0.2})
        assert result["cluster_id"] >= 0


class TestIsolationForest:
    def test_predict_unfitted(self):
        """미학습 상태에서 Z-score fallback."""
        detector = SpendAnomalyDetector()
        txs = [
            {"amount": 10000, "hour": 12, "is_domestic": True, "category_idx": 0},
            {"amount": 12000, "hour": 13, "is_domestic": True, "category_idx": 0},
            {"amount": 500000, "hour": 3, "is_domestic": False, "category_idx": 1},
        ]
        results = detector.predict(txs)
        assert len(results) == 3
        # 500,000원은 이상치로 감지되어야 함
        assert results[2]["anomaly_score"] < results[0]["anomaly_score"]

    def test_fit_and_predict(self):
        detector = SpendAnomalyDetector()
        txs = [{"amount": 10000 + i * 500, "hour": 12, "is_domestic": True, "category_idx": 0}
               for i in range(50)]
        detector.fit(txs)
        assert detector.is_fitted

        test_txs = [
            {"amount": 12000, "hour": 12, "is_domestic": True, "category_idx": 0},
            {"amount": 999999, "hour": 3, "is_domestic": False, "category_idx": 5},
        ]
        results = detector.predict(test_txs)
        assert len(results) == 2


class TestForecaster:
    def test_predict_moving_avg(self):
        """데이터 부족 시 가중이동평균 fallback."""
        forecaster = SpendForecaster()
        result = forecaster.predict([100000, 120000, 110000])
        assert result["method"] == "weighted_moving_avg"
        assert result["predicted"] > 0
        assert result["confidence"] > 0

    def test_predict_no_data(self):
        forecaster = SpendForecaster()
        result = forecaster.predict([])
        assert result["method"] == "no_data"
        assert result["predicted"] == 0


class TestOverspendClassifier:
    def test_predict_rule_based(self):
        """미학습 상태에서 규칙 기반 fallback."""
        clf = OverspendClassifier()
        features = clf.build_features(
            amount=100000, avg_amount=30000, category_pct=0.5,
            hour=14, is_domestic=True,
            monthly_total=1500000, monthly_avg=1000000,
            recent_tx_count=50,
        )
        result = clf.predict(features)
        assert result["method"] == "rule_based"
        assert 0 <= result["probability"] <= 1
        # amount_ratio > 3 이므로 0.4 이상이어야 함
        assert result["probability"] >= 0.4

    def test_build_features_shape(self):
        clf = OverspendClassifier()
        features = clf.build_features(
            amount=50000, avg_amount=25000, category_pct=0.3,
            hour=12, is_domestic=True,
            monthly_total=800000, monthly_avg=750000,
            recent_tx_count=30,
        )
        assert features.shape == (1, 7)
