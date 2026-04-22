"""Isolation Forest 이상 지출 탐지.

xlsx 참고: 이상치 탐지 — Isolation Forest
  → 특이 거래 발견 및 평소 거래 기준
  → 비지도 / 로그 데이터

capstone의 model_bundle_open_full.joblib 에 포함된
Isolation Forest 모델을 재활용하거나, 소비 특화 모델을 별도 학습.
"""

import numpy as np
from sklearn.ensemble import IsolationForest

from app.config import settings


class SpendAnomalyDetector:
    """소비 패턴 기반 이상 지출 탐지."""

    FEATURE_NAMES = ["amount", "hour", "is_domestic", "category_idx", "amount_log"]

    def __init__(self, contamination: float = 0.05, random_state: int = 42):
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100,
        )
        self.is_fitted = False
        self.threshold = settings.ANOMALY_THRESHOLD
        self.train_mean_: np.ndarray | None = None
        self.train_std_: np.ndarray | None = None

    def fit(self, transactions: list[dict]) -> None:
        """거래 데이터로 모델 학습.

        Args:
            transactions: [{"amount": 50000, "hour": 14, "category_idx": 0, ...}, ...]
        """
        if len(transactions) < 10:
            return

        X = self._to_matrix(transactions)
        self.model.fit(X)
        self.is_fitted = True
        # Feature Attribution을 위한 학습 통계 저장
        self.train_mean_ = X.mean(axis=0)
        self.train_std_ = X.std(axis=0) + 1e-8  # 0 나눔 방지

    def _to_matrix(self, transactions: list[dict]) -> np.ndarray:
        """거래 데이터 → 특성 행렬.

        Features: [amount, hour, is_domestic, category_index, amount_log]
        """
        rows = []
        for tx in transactions:
            amount = tx.get("amount", 0)
            rows.append([
                amount,
                tx.get("hour", 12),
                1 if tx.get("is_domestic", True) else 0,
                tx.get("category_idx", 0),
                np.log1p(amount),
            ])
        return np.array(rows)

    def predict(self, transactions: list[dict]) -> list[dict]:
        """이상 지출 탐지.

        Returns:
            [{"index": 0, "anomaly_score": -0.8, "is_anomaly": True}, ...]
        """
        if not transactions:
            return []

        X = self._to_matrix(transactions)

        if not self.is_fitted:
            # 미학습 상태: 통계적 fallback (평균 대비 3σ)
            amounts = X[:, 0]
            mean, std = amounts.mean(), amounts.std()
            results = []
            for i, row in enumerate(X):
                if std > 0:
                    z = (row[0] - mean) / std
                    is_anomaly = z > 3 or z < -3
                    score = -abs(z) / 10
                else:
                    is_anomaly = False
                    score = 0.0
                results.append({
                    "index": i,
                    "anomaly_score": round(float(score), 4),
                    "is_anomaly": is_anomaly,
                })
            return results

        scores = self.model.decision_function(X)
        preds = self.model.predict(X)

        results = []
        for i in range(len(X)):
            results.append({
                "index": i,
                "anomaly_score": round(float(scores[i]), 4),
                "is_anomaly": int(preds[i]) == -1,
            })
        return results


    def explain(self, transactions: list[dict]) -> list[dict]:
        """Feature별 편차 계산으로 이상 거래 설명.

        Returns:
            [{contributions: {feature: deviation_sigma}, top_factor, ...}]
        """
        if not transactions:
            return []

        X = self._to_matrix(transactions)
        results = []
        for row in X:
            if self.train_mean_ is not None:
                devs = (row - self.train_mean_) / self.train_std_
            else:
                devs = row * 0  # 학습 전: 편차 0

            contributions = {
                fname: round(float(devs[i]), 4)
                for i, fname in enumerate(self.FEATURE_NAMES)
            }
            top = max(contributions, key=lambda k: abs(contributions[k]))
            results.append({
                "contributions": contributions,
                "top_factor": top,
            })
        return results


# 싱글턴
anomaly_detector = SpendAnomalyDetector()
