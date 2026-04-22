"""XAI (Explainable AI) 스키마."""

from pydantic import BaseModel


class ShapFeature(BaseModel):
    feature: str
    feature_kr: str
    value: float
    shap_value: float


class ShapExplanation(BaseModel):
    user_id: str
    base_value: float
    prediction: float
    is_overspend: bool
    features: list[ShapFeature]
    top_factor: str
    top_factor_kr: str
    summary_text: str
    method: str = "shap"


class AnomalyFeatureContribution(BaseModel):
    feature: str
    feature_kr: str
    deviation: float  # 표준편차 단위 편차


class AnomalyExplanation(BaseModel):
    transaction_id: str
    amount: float
    category: str
    anomaly_score: float
    is_anomaly: bool
    contributions: list[AnomalyFeatureContribution]
    top_factor: str
    top_factor_kr: str
    reason: str


class AnomalyExplanationList(BaseModel):
    user_id: str
    explanations: list[AnomalyExplanation]
    total_anomalies: int


class ClusterFeatureDeviation(BaseModel):
    category: str
    category_kr: str
    user_value: float
    center_value: float
    deviation: float


class ClusterExplanation(BaseModel):
    user_id: str
    cluster_id: int
    cluster_label: str
    distances_to_centers: list[dict]  # [{"cluster": 0, "label": "절약형", "distance": 1.23}]
    feature_deviations: list[ClusterFeatureDeviation]
    top_pull_toward: str  # 이 카테고리가 현재 군집으로 끌어당김
    top_pull_away: str    # 이 카테고리가 다른 군집으로 밀어냄
    summary_text: str
