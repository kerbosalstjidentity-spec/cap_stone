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


    def explain(self, category_pcts: dict[str, float]) -> dict:
        """클러스터 귀속 이유 — 클러스터 중심과의 per-feature 차이.

        Returns:
            {cluster_label, distances_to_centers, feature_deviations, top_pull_toward, top_pull_away, summary_text}
        """
        vec = self._build_feature_vector(category_pcts).reshape(1, -1)

        if not self.is_fitted:
            return {
                "cluster_label": self.predict(category_pcts)["cluster_label"],
                "distances_to_centers": [],
                "feature_deviations": [],
                "top_pull_toward": "",
                "top_pull_away": "",
                "summary_text": "모델 학습 후 상세 설명이 제공됩니다.",
            }

        vec_scaled = self.scaler.transform(vec)
        cluster_id = int(self.model.predict(vec_scaled)[0])
        label = self.cluster_labels.get(cluster_id, f"군집_{cluster_id}")
        centers = self.model.cluster_centers_  # scaled 좌표

        # 각 클러스터까지 거리
        dists = [
            {
                "cluster": i,
                "label": self.cluster_labels.get(i, f"군집_{i}"),
                "distance": round(float(np.linalg.norm(vec_scaled - centers[i])), 4),
            }
            for i in range(self.n_clusters)
        ]

        # 할당 클러스터와의 feature 편차 (원래 스케일)
        center_orig = self.scaler.inverse_transform(centers[cluster_id].reshape(1, -1))[0]
        user_vec = vec[0]
        deviations = []
        for i, cat in enumerate(FEATURE_CATEGORIES):
            diff = float(user_vec[i]) - float(center_orig[i])
            deviations.append({
                "category": cat.value,
                "category_kr": _CAT_KR.get(cat.value, cat.value),
                "user_value": round(float(user_vec[i]), 4),
                "center_value": round(float(center_orig[i]), 4),
                "deviation": round(diff, 4),
            })

        deviations.sort(key=lambda x: abs(x["deviation"]), reverse=True)
        toward = next((d for d in deviations if d["deviation"] < 0), {}).get("category_kr", "")
        away = next((d for d in deviations if d["deviation"] > 0), {}).get("category_kr", "")

        summary = f"'{label}' 유형 — "
        if away:
            summary += f"{away} 지출이 군집 평균보다 높음"
        if toward:
            summary += f", {toward} 지출이 낮음"

        return {
            "cluster_label": label,
            "distances_to_centers": sorted(dists, key=lambda x: x["distance"]),
            "feature_deviations": deviations,
            "top_pull_toward": toward,
            "top_pull_away": away,
            "summary_text": summary,
        }


_CAT_KR = {
    "food": "식비", "shopping": "쇼핑", "transport": "교통",
    "entertainment": "여가", "education": "교육", "healthcare": "의료",
    "housing": "주거", "utilities": "공과금", "finance": "금융",
    "travel": "여행", "other": "기타",
}

# 싱글턴
cluster_model = SpendClusterModel()
