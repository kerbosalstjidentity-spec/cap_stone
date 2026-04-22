"""감정×소비 분석 스키마."""

from datetime import datetime
from pydantic import BaseModel, Field


class EmotionTagCreate(BaseModel):
    user_id: str
    transaction_id: str
    emotion: str = Field(pattern="^(happy|stressed|bored|reward|impulse|neutral)$")
    intensity: int = Field(default=3, ge=1, le=5)
    note: str = ""


class EmotionTagResponse(BaseModel):
    id: int
    user_id: str
    transaction_id: str
    emotion: str
    intensity: int
    note: str
    created_at: datetime
    # 거래 정보 (JOIN)
    amount: float | None = None
    category: str | None = None
    timestamp: datetime | None = None


class EmotionCorrelationItem(BaseModel):
    emotion: str
    emotion_kr: str
    category: str
    category_kr: str
    avg_amount: float
    count: int
    total_amount: float
    multiplier: float  # 전체 평균 대비 배수


class EmotionCorrelationResponse(BaseModel):
    user_id: str
    correlations: list[EmotionCorrelationItem]
    overall_avg: float


class HeatmapCell(BaseModel):
    category: str
    category_kr: str
    value: float  # 정규화된 값 (0~1)
    raw_avg: float
    count: int


class HeatmapRow(BaseModel):
    emotion: str
    emotion_kr: str
    cells: list[HeatmapCell]


class EmotionHeatmapResponse(BaseModel):
    user_id: str
    rows: list[HeatmapRow]
    max_value: float


class RiskFactor(BaseModel):
    factor: str
    weight: float
    description: str


class ImpulseRiskResponse(BaseModel):
    user_id: str
    risk_score: float  # 0~1
    risk_level: str   # safe / caution / warning / danger
    warning_message: str
    risk_factors: list[RiskFactor]
    current_hour: int
    current_day: str


class EmotionInsight(BaseModel):
    insight_text: str
    emotion: str
    emotion_kr: str
    related_category: str
    category_kr: str
    multiplier: float
    severity: str  # info / warning / danger


class EmotionInsightResponse(BaseModel):
    user_id: str
    insights: list[EmotionInsight]
