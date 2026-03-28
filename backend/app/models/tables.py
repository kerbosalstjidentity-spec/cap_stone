"""전체 ORM 테이블 정의 — 소비 프로필 + 교육 프로그램."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  사용자
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    nickname: Mapped[str] = mapped_column(String(100), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupation: Mapped[str] = mapped_column(String(100), default="")  # 직업
    monthly_income: Mapped[float | None] = mapped_column(Float, nullable=True)  # 월 수입
    edu_level: Mapped[str] = mapped_column(String(20), default="beginner")  # beginner/intermediate/advanced
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # relationships
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    course_progress: Mapped[list["CourseProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    challenge_enrollments: Mapped[list["ChallengeEnrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    badges: Mapped[list["UserBadge"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    quiz_scores: Mapped[list["QuizScore"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  거래 내역
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_tx_user_ts", "user_id", "timestamp"),
        Index("ix_tx_user_category", "user_id", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")  # food, shopping, ...
    channel: Mapped[str] = mapped_column(String(16), default="app")  # app / web / offline
    is_domestic: Mapped[bool] = mapped_column(Boolean, default=True)
    memo: Mapped[str] = mapped_column(Text, default="")

    # relationships
    user: Mapped["User"] = relationship(back_populates="transactions")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  소비 프로필 캐시 (집계)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SpendProfileCache(TimestampMixin, Base):
    """월별 카테고리 집계 캐시 — 쿼리 성능을 위해 미리 계산."""
    __tablename__ = "spend_profile_cache"
    __table_args__ = (
        Index("ix_spc_user_period", "user_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-03"
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    tx_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_amount: Mapped[float] = mapped_column(Float, default=0)
    max_amount: Mapped[float] = mapped_column(Float, default=0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  예산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        Index("ix_budget_user_period", "user_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-03"
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_amount: Mapped[float] = mapped_column(Float, nullable=False)
    monthly_total: Mapped[float] = mapped_column(Float, default=0)  # 전체 예산 합계

    user: Mapped["User"] = relationship(back_populates="budgets")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  교육 — 코스 진행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CourseProgress(TimestampMixin, Base):
    __tablename__ = "course_progress"
    __table_args__ = (
        Index("ix_cp_user_course", "user_id", "course_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(32), nullable=False)  # L1_C1, L2_C3, ...
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="course_progress")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  교육 — 챌린지 참여
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ChallengeEnrollment(TimestampMixin, Base):
    __tablename__ = "challenge_enrollments"
    __table_args__ = (
        Index("ix_ce_user_challenge", "user_id", "challenge_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    challenge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / completed / failed
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_value: Mapped[float] = mapped_column(Float, default=0)
    target_value: Mapped[float] = mapped_column(Float, default=1.0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0)

    user: Mapped["User"] = relationship(back_populates="challenge_enrollments")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  교육 — 배지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserBadge(TimestampMixin, Base):
    __tablename__ = "user_badges"
    __table_args__ = (
        Index("ix_ub_user_badge", "user_id", "badge_name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    badge_name: Mapped[str] = mapped_column(String(64), nullable=False)
    badge_icon: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    challenge_id: Mapped[str] = mapped_column(String(64), default="")
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="badges")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  교육 — 퀴즈 기록
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QuizScore(TimestampMixin, Base):
    __tablename__ = "quiz_scores"
    __table_args__ = (
        Index("ix_qs_user_type", "user_id", "quiz_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    quiz_type: Mapped[str] = mapped_column(String(32), nullable=False)  # fraud / spending
    score: Mapped[float] = mapped_column(Float, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="quiz_scores")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  리더보드 포인트 (집계용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LeaderboardPoints(TimestampMixin, Base):
    __tablename__ = "leaderboard_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    badge_count: Mapped[int] = mapped_column(Integer, default=0)
    challenge_completed: Mapped[int] = mapped_column(Integer, default=0)
    quiz_score_avg: Mapped[float] = mapped_column(Float, default=0)
