"""교육 프로그램 — DB 기반 저장소 (Phase 2).

정적 콘텐츠(COURSES, CHALLENGES)는 education_store의 것을 재사용하고,
진행 상태·배지·퀴즈 점수·리더보드는 PostgreSQL에 저장.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.redis import cache_get, cache_set
from app.models.tables import (
    Budget,
    ChallengeEnrollment as DBChallengeEnrollment,
    CourseProgress as DBCourseProgress,
    LeaderboardPoints,
    QuizScore,
    Transaction,
    User,
    UserBadge,
)
# 정적 콘텐츠는 기존 store에서 재사용
from app.services.education_store import CHALLENGES, COURSES
from app.schemas.education import (
    Badge,
    ChallengeEnrollment,
    ChallengeStatus,
    CourseProgress,
    LeaderboardEntry,
)


# ──────────────────────────────────────────────
#  코스 진행 (CourseProgress)
# ──────────────────────────────────────────────

async def get_course_progress(user_id: str, course_id: str, session: AsyncSession) -> CourseProgress | None:
    result = await session.execute(
        select(DBCourseProgress).where(
            DBCourseProgress.user_id == user_id,
            DBCourseProgress.course_id == course_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return CourseProgress(
        user_id=row.user_id,
        course_id=row.course_id,
        current_step=row.current_step,
        total_steps=row.total_steps,
        completed=row.completed,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


async def advance_course_step(user_id: str, course_id: str, session: AsyncSession) -> CourseProgress:
    """코스 스텝을 1 전진. 없으면 생성."""
    course = COURSES.get(course_id)
    if not course:
        raise ValueError(f"Unknown course: {course_id}")

    result = await session.execute(
        select(DBCourseProgress).where(
            DBCourseProgress.user_id == user_id,
            DBCourseProgress.course_id == course_id,
        )
    )
    row = result.scalar_one_or_none()

    if not row:
        row = DBCourseProgress(
            user_id=user_id,
            course_id=course_id,
            current_step=1,
            total_steps=course.total_steps,
        )
        session.add(row)
        await session.flush()
    else:
        if not row.completed:
            next_step = min(row.current_step + 1, row.total_steps)
            row.current_step = next_step
            if next_step == row.total_steps:
                row.completed = True
                row.completed_at = datetime.now(UTC)
                # 코스 완료 배지 부여
                await _award_course_badge(user_id, course_id, course.title, session)

    await session.commit()
    await session.refresh(row)

    return CourseProgress(
        user_id=row.user_id,
        course_id=row.course_id,
        current_step=row.current_step,
        total_steps=row.total_steps,
        completed=row.completed,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


async def get_all_progress(user_id: str, session: AsyncSession) -> list[CourseProgress]:
    result = await session.execute(
        select(DBCourseProgress).where(DBCourseProgress.user_id == user_id)
    )
    rows = result.scalars().all()
    return [
        CourseProgress(
            user_id=r.user_id,
            course_id=r.course_id,
            current_step=r.current_step,
            total_steps=r.total_steps,
            completed=r.completed,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]


# ──────────────────────────────────────────────
#  챌린지 (ChallengeEnrollment)
# ──────────────────────────────────────────────

async def enroll_challenge(user_id: str, challenge_id: str, session: AsyncSession) -> ChallengeEnrollment:
    challenge = CHALLENGES.get(challenge_id)
    if not challenge:
        raise ValueError(f"Unknown challenge: {challenge_id}")

    # users 테이블에 row가 없으면 FK 위반 → 없으면 먼저 생성
    existing_user = await session.execute(select(User).where(User.user_id == user_id))
    if existing_user.scalar_one_or_none() is None:
        session.add(User(user_id=user_id))
        await session.flush()

    # 이미 참여 중이면 반환
    result = await session.execute(
        select(DBChallengeEnrollment).where(
            DBChallengeEnrollment.user_id == user_id,
            DBChallengeEnrollment.challenge_id == challenge_id,
            DBChallengeEnrollment.status == "active",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return _to_enrollment_schema(existing)

    now = datetime.now(UTC)
    row = DBChallengeEnrollment(
        user_id=user_id,
        challenge_id=challenge_id,
        status="active",
        start_date=now,
        end_date=now + timedelta(days=challenge.duration_days),
        target_value=challenge.target_value,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_enrollment_schema(row)


async def update_challenge_progress(
    user_id: str,
    challenge_id: str,
    current_value: float,
    session: AsyncSession,
) -> ChallengeEnrollment:
    result = await session.execute(
        select(DBChallengeEnrollment).where(
            DBChallengeEnrollment.user_id == user_id,
            DBChallengeEnrollment.challenge_id == challenge_id,
            DBChallengeEnrollment.status == "active",
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError("활성 챌린지를 찾을 수 없습니다.")

    row.current_value = current_value
    row.progress_pct = min(current_value / row.target_value * 100, 100) if row.target_value > 0 else 0

    if row.progress_pct >= 100:
        row.status = "completed"
        await _award_challenge_badge(user_id, challenge_id, session)

    await session.commit()
    await session.refresh(row)
    return _to_enrollment_schema(row)


async def get_user_challenges(user_id: str, session: AsyncSession) -> list[ChallengeEnrollment]:
    result = await session.execute(
        select(DBChallengeEnrollment).where(DBChallengeEnrollment.user_id == user_id)
        .order_by(DBChallengeEnrollment.created_at.desc())
    )
    return [_to_enrollment_schema(r) for r in result.scalars().all()]


async def sync_challenge_progress(user_id: str, session: AsyncSession) -> None:
    """활성 챌린지의 진행률을 소비 데이터 기반으로 자동 계산·업데이트."""
    active = (await session.execute(
        select(DBChallengeEnrollment).where(
            DBChallengeEnrollment.user_id == user_id,
            DBChallengeEnrollment.status == "active",
        )
    )).scalars().all()

    if not active:
        return

    now = datetime.now(UTC)

    # 최근 30일 트랜잭션 로드 (한 번만)
    cutoff = now - timedelta(days=30)
    tx_rows = (await session.execute(
        select(Transaction.timestamp, Transaction.category, Transaction.amount)
        .where(Transaction.user_id == user_id, Transaction.timestamp >= cutoff)
        .order_by(Transaction.timestamp)
    )).all()

    # 퀴즈 점수 로드 (fraud_quiz_master용)
    quiz_rows = (await session.execute(
        select(QuizScore.score, QuizScore.created_at)
        .where(QuizScore.user_id == user_id)
        .order_by(QuizScore.created_at)
    )).all()

    for enrollment in active:
        metric = CHALLENGES.get(enrollment.challenge_id)
        if not metric:
            continue

        value = _compute_metric(
            metric.target_metric, enrollment, tx_rows, quiz_rows, now, session
        )
        if value is None:
            continue

        enrollment.current_value = value
        enrollment.progress_pct = min(value / enrollment.target_value * 100, 100) if enrollment.target_value > 0 else 0

        if enrollment.progress_pct >= 100:
            enrollment.status = "completed"
            await _award_challenge_badge(user_id, enrollment.challenge_id, session)

    await session.commit()


def _compute_metric(
    target_metric: str,
    enrollment: DBChallengeEnrollment,
    tx_rows: list,
    quiz_rows: list,
    now: datetime,
    session,
) -> float | None:
    """메트릭별 현재 달성값 계산."""

    if target_metric == "food_cafe_reduction":
        # 등록 전달 대비 등록 후 식비 감소율 (%)
        start = enrollment.start_date
        prev_month = (start - timedelta(days=30))
        before = sum(r.amount for r in tx_rows if r.category in ("food", "cafe") and prev_month <= r.timestamp < start)
        after = sum(r.amount for r in tx_rows if r.category in ("food", "cafe") and r.timestamp >= start)
        if before <= 0:
            return 0.0
        reduction_pct = max((before - after) / before * 100, 0)
        return round(reduction_pct, 1)

    elif target_metric == "zero_spend_days":
        # 챌린지 기간(7일) 내 무지출 일수
        start = enrollment.start_date
        end = min(enrollment.end_date, now)
        spend_days = {r.timestamp.date() for r in tx_rows if start <= r.timestamp <= end}
        total_days = (end.date() - start.date()).days + 1
        zero_days = max(total_days - len(spend_days), 0)
        return float(zero_days)

    elif target_metric == "budget_compliance":
        # 이번 달 예산 준수율: (1 - 초과율) * 100, 예산 정보 없으면 0
        current_period = now.strftime("%Y-%m")
        month_spend = sum(r.amount for r in tx_rows if r.timestamp.strftime("%Y-%m") == current_period)
        # 간단히: 지출이 0이면 100%, 지출이 많을수록 낮아짐 (예산 DB 없으면 기준 200만)
        budget_ref = 2_000_000.0
        compliance = max((1 - month_spend / budget_ref) * 100, 0) if budget_ref > 0 else 0
        return round(compliance, 1)

    elif target_metric == "fraud_quiz_streak":
        # 연속 정답 최대 streak
        if not quiz_rows:
            return 0.0
        streak = 0
        best = 0
        for q in quiz_rows:
            if q.score >= 60:  # 60점 이상 = 정답
                streak += 1
                best = max(best, streak)
            else:
                streak = 0
        return float(best)

    elif target_metric == "cluster_change":
        # 소비 패턴 변화는 자동 계산 어려움 → 수동 진행률 유지
        return None

    return None


# ──────────────────────────────────────────────
#  배지
# ──────────────────────────────────────────────

async def get_badges(user_id: str, session: AsyncSession) -> list[Badge]:
    result = await session.execute(
        select(UserBadge).where(UserBadge.user_id == user_id).order_by(UserBadge.earned_at.desc())
    )
    rows = result.scalars().all()
    return [
        Badge(
            badge_name=r.badge_name,
            badge_icon=r.badge_icon,
            description=r.description,
            challenge_id=r.challenge_id,
            earned_at=r.earned_at,
        )
        for r in rows
    ]


# ──────────────────────────────────────────────
#  퀴즈 점수
# ──────────────────────────────────────────────

async def save_quiz_score(
    user_id: str,
    quiz_type: str,
    score: float,
    total_questions: int,
    correct_count: int,
    session: AsyncSession,
) -> None:
    row = QuizScore(
        user_id=user_id,
        quiz_type=quiz_type,
        score=score,
        total_questions=total_questions,
        correct_count=correct_count,
    )
    session.add(row)
    await session.flush()
    await _update_leaderboard(user_id, session)
    await session.commit()


async def get_quiz_scores(user_id: str, session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(QuizScore).where(QuizScore.user_id == user_id).order_by(QuizScore.taken_at.desc())
    )
    return [
        {
            "quiz_type": r.quiz_type,
            "score": r.score,
            "correct_count": r.correct_count,
            "total_questions": r.total_questions,
            "taken_at": r.taken_at.isoformat(),
        }
        for r in result.scalars().all()
    ]


# ──────────────────────────────────────────────
#  리더보드
# ──────────────────────────────────────────────

async def get_leaderboard(session: AsyncSession, limit: int = 10) -> list[LeaderboardEntry]:
    cache_key = "leaderboard:top"
    cached = await cache_get(cache_key)
    if cached:
        return [LeaderboardEntry(**e) for e in cached]

    result = await session.execute(
        select(LeaderboardPoints)
        .order_by(LeaderboardPoints.total_points.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    entries = [
        LeaderboardEntry(
            rank=idx + 1,
            user_id=r.user_id,
            total_points=r.total_points,
            badge_count=r.badge_count,
            challenge_completed=r.challenge_completed,
            quiz_score_avg=r.quiz_score_avg,
        )
        for idx, r in enumerate(rows)
    ]
    await cache_set(cache_key, [e.model_dump() for e in entries], settings.CACHE_TTL_LEADERBOARD)
    return entries


# ──────────────────────────────────────────────
#  내부 헬퍼
# ──────────────────────────────────────────────

def _to_enrollment_schema(row: DBChallengeEnrollment) -> ChallengeEnrollment:
    return ChallengeEnrollment(
        user_id=row.user_id,
        challenge_id=row.challenge_id,
        status=ChallengeStatus(row.status),
        start_date=row.start_date,
        end_date=row.end_date,
        current_value=row.current_value,
        target_value=row.target_value,
        progress_pct=row.progress_pct,
    )


async def _award_badge(
    user_id: str,
    badge_name: str,
    icon: str,
    description: str,
    challenge_id: str,
    session: AsyncSession,
) -> None:
    """중복 없이 배지 부여."""
    existing = await session.execute(
        select(UserBadge).where(
            UserBadge.user_id == user_id,
            UserBadge.badge_name == badge_name,
        )
    )
    if existing.scalar_one_or_none():
        return
    badge = UserBadge(
        user_id=user_id,
        badge_name=badge_name,
        badge_icon=icon,
        description=description,
        challenge_id=challenge_id,
    )
    session.add(badge)
    await session.flush()
    await _update_leaderboard(user_id, session)


async def _award_course_badge(user_id: str, course_id: str, course_title: str, session: AsyncSession) -> None:
    await _award_badge(
        user_id,
        badge_name=f"코스완료_{course_id}",
        icon="🎓",
        description=f"'{course_title}' 코스를 완료했습니다!",
        challenge_id="",
        session=session,
    )


async def _award_challenge_badge(user_id: str, challenge_id: str, session: AsyncSession) -> None:
    challenge = CHALLENGES.get(challenge_id)
    if challenge:
        badge_name = challenge.badge_name
        icon = challenge.badge_icon
        description = f"'{challenge.name}' 챌린지를 달성했습니다!"
    else:
        badge_name = f"챌린지완료_{challenge_id}"
        icon = "trophy"
        description = f"'{challenge_id}' 챌린지를 달성했습니다!"
    await _award_badge(
        user_id,
        badge_name=badge_name,
        icon=icon,
        description=description,
        challenge_id=challenge_id,
        session=session,
    )


async def _update_leaderboard(user_id: str, session: AsyncSession) -> None:
    """리더보드 포인트 재계산 및 upsert."""
    badge_result = await session.execute(
        select(func.count()).where(UserBadge.user_id == user_id)
    )
    badge_count = badge_result.scalar() or 0

    challenge_result = await session.execute(
        select(func.count()).where(
            DBChallengeEnrollment.user_id == user_id,
            DBChallengeEnrollment.status == "completed",
        )
    )
    challenge_completed = challenge_result.scalar() or 0

    quiz_result = await session.execute(
        select(func.avg(QuizScore.score)).where(QuizScore.user_id == user_id)
    )
    quiz_avg = float(quiz_result.scalar() or 0)

    total_points = badge_count * 50 + challenge_completed * 100 + int(quiz_avg * 10)

    existing = await session.execute(
        select(LeaderboardPoints).where(LeaderboardPoints.user_id == user_id)
    )
    lb = existing.scalar_one_or_none()
    if lb:
        lb.badge_count = badge_count
        lb.challenge_completed = challenge_completed
        lb.quiz_score_avg = quiz_avg
        lb.total_points = total_points
    else:
        session.add(LeaderboardPoints(
            user_id=user_id,
            badge_count=badge_count,
            challenge_completed=challenge_completed,
            quiz_score_avg=quiz_avg,
            total_points=total_points,
        ))
