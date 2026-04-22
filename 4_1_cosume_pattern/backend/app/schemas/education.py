"""교육 프로그램 스키마 — 진단, 코스, 챌린지, 퀴즈, 배지."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── 레벨 & 상태 ─────────────────────────────────────────────

class EduLevel(str, Enum):
    BEGINNER = "beginner"       # 기초반
    INTERMEDIATE = "intermediate"  # 중급반
    ADVANCED = "advanced"       # 고급반


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskGrade(str, Enum):
    SAFE = "safe"           # 안전
    CAUTION = "caution"     # 주의
    WARNING = "warning"     # 경고
    DANGER = "danger"       # 위험
    CRITICAL = "critical"   # 심각


# ── 소비 습관 진단 ────────────────────────────────────────────

class DiagnosisReport(BaseModel):
    user_id: str
    spend_type: str          # 절약형/균형형/소비형/투자형
    spend_type_description: str
    risk_grade: RiskGrade
    risk_score: float        # 0~1
    risk_description: str
    monthly_insight: str     # 전월 비교 인사이트
    anomaly_count: int
    anomaly_highlights: list[str]
    improvement_points: list[str]
    recommended_level: EduLevel
    recommended_courses: list[str]


# ── 교육 코스 ─────────────────────────────────────────────────

class CourseStep(BaseModel):
    step: int
    title: str
    content: str
    tip: str = ""
    interactive: str = ""    # 연동 API 힌트 (e.g., "budget_api", "category_chart")


class Course(BaseModel):
    course_id: str
    level: EduLevel
    title: str
    description: str
    steps: list[CourseStep]
    total_steps: int


class CourseProgress(BaseModel):
    user_id: str
    course_id: str
    current_step: int
    total_steps: int
    completed: bool
    started_at: datetime
    completed_at: datetime | None = None


class CurriculumAssignment(BaseModel):
    user_id: str
    assigned_level: EduLevel
    reason: str
    courses: list[Course]
    total_courses: int
    completed_courses: int


# ── 챌린지 & 배지 ────────────────────────────────────────────

class Challenge(BaseModel):
    challenge_id: str
    name: str
    description: str
    duration_days: int
    target_metric: str       # e.g., "food_spending", "zero_spend_days"
    target_description: str
    target_value: float = 100.0
    badge_name: str
    badge_icon: str


class ChallengeEnrollment(BaseModel):
    user_id: str
    challenge_id: str
    status: ChallengeStatus
    start_date: datetime
    end_date: datetime
    current_value: float
    target_value: float
    progress_pct: float


class Badge(BaseModel):
    badge_name: str
    badge_icon: str
    description: str
    earned_at: datetime
    challenge_id: str


# ── 퀴즈 ──────────────────────────────────────────────────────

class FraudQuizQuestion(BaseModel):
    question_id: str
    transaction_summary: str  # "새벽 3시, 해외IP, 150만원 전자제품 결제"
    amount: float
    hour: int
    is_foreign: bool
    category: str
    options: list[str]        # ["정상 거래", "의심 거래"]
    correct_answer: str
    explanation: str          # 해설
    triggered_rules: list[str]


class FraudQuizResult(BaseModel):
    user_id: str
    total_questions: int
    correct_count: int
    score_pct: float
    questions: list[FraudQuizQuestion]
    user_answers: list[str]


class SpendingQuizQuestion(BaseModel):
    question_id: str
    question: str
    options: list[str]
    correct_answer: str
    explanation: str
    category: str             # "budgeting", "saving", "investing", "fraud_prevention"


# ── 시뮬레이션 ────────────────────────────────────────────────

class SavingsSimulationRequest(BaseModel):
    user_id: str
    reduction_pct: dict[str, float] = Field(
        default_factory=dict,
        description="카테고리별 절감 비율 (0~1). e.g., {'food': 0.2, 'shopping': 0.3}"
    )
    months: int = Field(default=12, ge=1, le=60)


class SavingsSimulationResult(BaseModel):
    user_id: str
    current_monthly: float
    projected_monthly: float
    monthly_saving: float
    total_saving_over_period: float
    months: int
    category_savings: dict[str, float]
    before_after: dict[str, dict[str, float]]  # {"food": {"before": x, "after": y}}


class FraudSimulationRequest(BaseModel):
    amount: float = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    is_foreign_ip: bool = False
    category: str = "shopping"
    is_new_merchant: bool = False


class FraudSimulationResult(BaseModel):
    scenario: dict
    rules_triggered: list[dict]  # [{"rule": "AMOUNT_REVIEW", "action": "REVIEW", "reason": "..."}]
    final_action: str            # PASS / REVIEW / BLOCK
    risk_explanation: str
    prevention_tips: list[str]


# ── 리더보드 ──────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    badge_count: int
    challenge_completed: int
    quiz_score_avg: float
    total_points: int
