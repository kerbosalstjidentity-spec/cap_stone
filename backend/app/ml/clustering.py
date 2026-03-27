"""K-Means 소비 유형 군집화.

xlsx 참고: 군집 분석 — K-Means / GMM
  → 소비 그룹핑 (식비, 쇼핑비, 기타 등)
  → 비지도 학습, 속도 빠름

사용자의 카테고리별 지출 비율을 기반으로 소비 유형을 분류:
  - 절약형 / 균형형 / 소비형 / 투자형
"""

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from app.schemas.spend import SpendCategory

CLUSTER_LABELS = {
    0: "절약형",
    1: "균형형",
    2: "소비형",
    3: "투자형",
}

# 특성 벡터 순서 (카테고리별 지출 비율)
FEATURE_CATEGORIES = [
    SpendCategory.FOOD,
    SpendCategory.SHOPPING,
    SpendCategory.TRANSPORT,
    SpendCategory.ENTERTAINMENT,
    SpendCategory.EDUCATION,
    SpendCategory.HEALTHCARE,
    SpendCategory.HOUSING,
    SpendCategory.UTILITIES,
    SpendCategory.FINANCE,
    SpendCategory.TRAVEL,
    SpendCategory.OTHER,
]


class SpendClusterModel:
    """K-Means 기반 소비 유형 군집화 모델."""

    def __init__(self, n_clusters: int = 4, random_state: int = 42):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        self.is_fitted = False
        self.cluster_labels = dict(CLUSTER_LABELS)

    def _build_feature_vector(self, category_pcts: dict[str, float]) -> np.ndarray:
        """카테고리별 지출 비율 → 특성 벡터."""
        return np.array([category_pcts.get(c.value, 0.0) for c in FEATURE_CATEGORIES])

    def fit(self, user_profiles: list[dict[str, float]]) -> None:
        """다수 사용자의 카테고리 비율로 군집 학습.

        Args:
            user_profiles: [{"food": 0.3, "shopping": 0.2, ...}, ...]
        """
        if len(user_profiles) < self.n_clusters:
            return

        X = np.array([self._build_feature_vector(p) for p in user_profiles])
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_fitted = True

        # 군집 중심 기반으로 라벨 자동 매핑 (총지출 비율 기준)
        centers = self.scaler.inverse_transform(self.model.cluster_centers_)
        total_spend = centers.sum(axis=1)
        order = np.argsort(total_spend)
        labels = ["절약형", "균형형", "소비형", "투자형"]
        self.cluster_labels = {int(order[i]): labels[i] for i in range(min(len(order), len(labels)))}

    def predict(self, category_pcts: dict[str, float]) -> dict:
        """단일 사용자의 소비 유형 예측.

        Returns:
            {"cluster_id": 0, "cluster_label": "절약형", "features": [...]}
        """
        vec = self._build_feature_vector(category_pcts).reshape(1, -1)

        if not self.is_fitted:
            # 미학습 상태: 규칙 기반 fallback
            total = sum(category_pcts.values())
            if total < 0.3:
                return {"cluster_id": -1, "cluster_label": "절약형", "features": vec[0].tolist()}
            elif total < 0.6:
                return {"cluster_id": -1, "cluster_label": "균형형", "features": vec[0].tolist()}
            else:
                return {"cluster_id": -1, "cluster_label": "소비형", "features": vec[0].tolist()}

        X_scaled = self.scaler.transform(vec)
        cluster_id = int(self.model.predict(X_scaled)[0])
        label = self.cluster_labels.get(cluster_id, f"군집_{cluster_id}")

        return {
            "cluster_id": cluster_id,
            "cluster_label": label,
            "features": vec[0].tolist(),
        }


# 싱글턴
cluster_model = SpendClusterModel()
