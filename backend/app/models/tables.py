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
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)  # None = 소셜/FIDO only
    nickname: Mapped[str] = mapped_column(String(100), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupation: Mapped[str] = mapped_column(String(100), default="")  # 직업
    monthly_income: Mapped[float | None] = mapped_column(Float, nullable=True)  # 월 수입
    edu_level: Mapped[str] = mapped_column(String(20), default="beginner")  # beginner/intermediate/advanced
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)   # TOTP 2FA
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # W3-#7: 패스키/2FA 분실 시 사용할 일회용 백업 코드 (bcrypt-hashed, JSON list)
    backup_codes_json: Mapped[str] = mapped_column(Text, default="[]")

    # relationships
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    course_progress: Mapped[list["CourseProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    challenge_enrollments: Mapped[list["ChallengeEnrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    badges: Mapped[list["UserBadge"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    quiz_scores: Mapped[list["QuizScore"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    fido_credentials: Mapped[list["FidoCredential"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    emotion_tags: Mapped[list["EmotionTag"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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
    emotion_tag: Mapped["EmotionTag | None"] = relationship(back_populates="transaction", uselist=False)


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  보안 — FIDO2 / WebAuthn Credential
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FidoCredential(TimestampMixin, Base):
    __tablename__ = "fido_credentials"
    __table_args__ = (
        Index("ix_fido_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    credential_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # base64url
    public_key: Mapped[str] = mapped_column(Text, nullable=False)                  # CBOR base64
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    device_type: Mapped[str] = mapped_column(String(32), default="unknown")        # platform / cross-platform
    aaguid: Mapped[str] = mapped_column(String(64), default="")                    # authenticator AAGUID
    name: Mapped[str] = mapped_column(String(128), default="내 인증 장치")          # 사용자 지정 이름
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="fido_credentials")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  보안 — Step-up Auth 세션 (임시 챌린지 토큰)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StepUpSession(Base):
    __tablename__ = "stepup_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # fido / totp / sms
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  알림
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Notification(TimestampMixin, Base):
    """실시간 알림 — 예산 경고, 이상거래, 챌린지 달성, XAI 인사이트, 감정 위험."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_user_created", "user_id", "created_at"),
        Index("ix_notif_user_unread", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="notifications")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  감정 태그
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AuditChainEntry(TimestampMixin, Base):
    """W3-#1: backend 감사 체인 PG 영속화.

    routes_security_dashboard 의 in-memory `_AUDIT_CHAIN` 을 대체.
    각 행은 hash chain의 단일 블록 — block_hash 가 prev_hash 와 연결되어 변조 탐지 가능.
    """
    __tablename__ = "audit_chain_entries"
    __table_args__ = (
        Index("ix_audit_index", "block_index", unique=True),
        Index("ix_audit_user_action", "user_id", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(128), default="")
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    block_ts: Mapped[float] = mapped_column(Float, nullable=False)  # epoch seconds
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    block_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class EmotionTag(TimestampMixin, Base):
    """거래에 연결된 감정 태그 — 감정×소비 상관 분석용."""
    __tablename__ = "emotion_tags"
    __table_args__ = (
        Index("ix_emotion_user_tx", "user_id", "transaction_id", unique=True),
        Index("ix_emotion_user_emotion", "user_id", "emotion"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(128), ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False)
    emotion: Mapped[str] = mapped_column(String(16), nullable=False)  # happy / stressed / bored / reward / impulse / neutral
    intensity: Mapped[int] = mapped_column(Integer, default=3)  # 1~5
    note: Mapped[str] = mapped_column(Text, default="")

    user: Mapped["User"] = relationship(back_populates="emotion_tags")
    transaction: Mapped["Transaction"] = relationship(back_populates="emotion_tag")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  W6-#7: 학습 진행 상태 추적 (부분 실패 추적용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TrainingRun(Base):
    """``train_all()`` 한 회 실행 상태.

    - ``status``: ``running`` / ``success`` / ``partial`` / ``failed``
    - ``started_at`` / ``finished_at``: UTC
    - ``per_model_status``: 각 모델별 결과 JSON 직렬화 문자열
    - ``error``: 실패 시 메시지 일부 (1000자 컷)
    """
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    per_model_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
