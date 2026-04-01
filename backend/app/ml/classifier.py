"""XGBoost 과소비 확률 분류.

xlsx 참고: 분류 분석/회귀 — XGBoost / LightGBM
  → 데이터로 이상 지출 발생 가능성 분석
  → 지도 학습 (레이블)

과소비 여부를 이진 분류 (0: 정상, 1: 과소비).
capstone의 XGBoost 모델 패턴을 따르되 소비 특화 특성 사용.
"""

import numpy as np

try:
    from xgboost import XGBClassifier
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from app.config import settings


class OverspendClassifier:
    """과소비 확률 분류기."""

    def __init__(self):
        if XGB_AVAILABLE:
            self.model = XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                use_label_encoder=False,
                eval_metric="logloss",
            )
        else:
            self.model = None
        self.is_fitted = False
        self.threshold = settings.OVERSPEND_THRESHOLD
        self.feature_names = [
            "amount",
            "avg_amount_ratio",      # 이번 지출 / 평균 지출
            "category_pct",          # 해당 카테고리 비율
            "hour",                  # 거래 시간
            "is_domestic",           # 국내 여부
            "monthly_total_ratio",   # 이번달 누적 / 월평균
            "tx_frequency",          # 최근 거래 빈도
        ]

    def build_features(
        self,
        amount: float,
        avg_amount: float,
        category_pct: float,
        hour: int,
        is_domestic: bool,
        monthly_total: float,
        monthly_avg: float,
        recent_tx_count: int,
    ) -> np.ndarray:
        """특성 벡터 구성."""
        return np.array([[
            amount,
            amount / avg_amount if avg_amount > 0 else 0,
            category_pct,
            hour,
            1 if is_domestic else 0,
            monthly_total / monthly_avg if monthly_avg > 0 else 0,
            recent_tx_count,
        ]])

    def fit(self, X: np.ndarray, y: np.ndarray) -> dict:
        """과소비 분류 모델 학습.

        Args:
            X: (N, 7) 특성 행렬
            y: (N,) 0=정상, 1=과소비
        """
        if not XGB_AVAILABLE:
            return {"status": "skipped", "reason": "xgboost_not_installed"}
        if len(X) < 10:
            return {"status": "skipped", "reason": "insufficient_data"}

        self.model.fit(X, y)
        self.is_fitted = True
        return {"status": "trained", "n_samples": len(X)}

    def explain(self, features: np.ndarray) -> dict:
        """SHAP TreeExplainer로 과소비 예측 설명.

        Returns:
            {method, base_value, shap_values: {fname: val}, top_factor}
        """
        if not self.is_fitted or not XGB_AVAILABLE:
            return {"method": "unavailable", "base_value": 0.5, "shap_values": {}}

        try:
            import shap
            explainer = shap.TreeExplainer(self.model)
            shap_vals = explainer.shap_values(features)
            # shap_vals: (1, n_features) for binary classification
            vals = shap_vals[0] if shap_vals.ndim == 2 else shap_vals
            shap_dict = {
                fname: float(vals[i])
                for i, fname in enumerate(self.feature_names)
            }
            base_val = float(explainer.expected_value) if not hasattr(explainer.expected_value, '__len__') else float(explainer.expected_value[1])
            top = max(shap_dict, key=lambda k: abs(shap_dict[k]))
            return {
                "method": "shap",
                "base_value": round(base_val, 4),
                "shap_values": {k: round(v, 4) for k, v in shap_dict.items()},
                "top_factor": top,
            }
        except Exception:
            return {"method": "unavailable", "base_value": 0.5, "shap_values": {}}

    def predict(self, features: np.ndarray) -> dict:
        """과소비 확률 예측.

        Returns:
            {"probability": 0.82, "is_overspend": True, "method": "xgboost"|"rule_based"}
        """
        if self.is_fitted and XGB_AVAILABLE:
            proba = float(self.model.predict_proba(features)[0][1])
            return {
                "probability": round(proba, 4),
                "is_overspend": proba >= self.threshold,
                "method": "xgboost",
            }

        # Fallback: 규칙 기반
        amount_ratio = features[0][1] if features.shape[1] > 1 else 0
        monthly_ratio = features[0][5] if features.shape[1] > 5 else 0

        score = 0.0
        if amount_ratio > 3:
            score += 0.4
        elif amount_ratio > 2:
            score += 0.2
        if monthly_ratio > 1.2:
            score += 0.3
        elif monthly_ratio > 1.0:
            score += 0.1
        if features[0][2] > 0.4:  # category_pct
            score += 0.2

        score = min(score, 1.0)
        return {
            "probability": round(score, 4),
            "is_overspend": score >= self.threshold,
            "method": "rule_based",
        }


# 싱글턴
overspend_classifier = OverspendClassifier()
