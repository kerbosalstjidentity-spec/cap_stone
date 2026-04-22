"""소비 패턴 분석용 데이터 스키마 — capstone schema_v2_open_mock 확장."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── 카테고리 분류 (MCC 기반 매핑) ──────────────────────────────

class SpendCategory(str, Enum):
    FOOD = "food"
    SHOPPING = "shopping"
    TRANSPORT = "transport"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    HOUSING = "housing"
    UTILITIES = "utilities"
    FINANCE = "finance"
    TRAVEL = "travel"
    OTHER = "other"


# ── 거래 입력 ─────────────────────────────────────────────────

class TransactionIngest(BaseModel):
    transaction_id: str
    user_id: str
    amount: float = Field(ge=0)
    timestamp: datetime
    merchant_id: str = ""
    category: SpendCategory = SpendCategory.OTHER
    channel: str = "app"  # app / web / offline
    is_domestic: bool = True
    memo: str = ""


class TransactionBatchIngest(BaseModel):
    transactions: list[TransactionIngest] = Field(max_length=1000)


# ── 소비 프로필 응답 ─────────────────────────────────────────

class CategorySummary(BaseModel):
    category: SpendCategory
    total_amount: float
    tx_count: int
    avg_amount: float
    pct_of_total: float  # 전체 지출 대비 비율 (0~1)


class SpendProfile(BaseModel):
    user_id: str
    total_tx_count: int
    total_amount: float
    avg_amount: float
    max_amount: float
    peak_hour: int  # 가장 많이 소비하는 시간대 (0~23)
    top_category: SpendCategory
    category_breakdown: list[CategorySummary]
    cluster_label: str = ""  # K-Means 결과: 절약형/균형형/과소비형/투자형
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── 분석 응답 ────────────────────────────────────────────────

class AnomalyItem(BaseModel):
    transaction_id: str
    amount: float
    category: SpendCategory
    anomaly_score: float
    timestamp: datetime
    reason: str  # 이상 사유


class TrendPoint(BaseModel):
    period: str  # "2026-03" 형식
    total_amount: float
    category_amounts: dict[str, float]


class ForecastResult(BaseModel):
    user_id: str
    forecast_period: str
    predicted_total: float
    predicted_by_category: dict[str, float]
    confidence: float


class ComparisonResult(BaseModel):
    user_id: str
    current_period: str
    previous_period: str
    current_total: float  # 당월 총액
    previous_total: float  # 전월 총액
    total_diff: float  # 금액 차이
    total_diff_pct: float  # 변화율 (%)
    category_diffs: dict[str, float]
    insight: str  # 한줄 요약


# ── 전략 제안 ────────────────────────────────────────────────

class BudgetItem(BaseModel):
    category: SpendCategory
    budget_amount: float = Field(ge=0)


class BudgetSet(BaseModel):
    user_id: str
    monthly_total: float = Field(ge=0)
    items: list[BudgetItem]


class StrategyRecommendation(BaseModel):
    user_id: str
    cluster_label: str
    recommendations: list[str]
    saving_opportunities: list[dict]  # {"category": ..., "potential_saving": ..., "reason": ...}
    risk_score: float  # 과소비 위험도 (0~1)
