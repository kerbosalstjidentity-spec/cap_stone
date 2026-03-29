"""소비 프로필 — DB 기반 저장소 (Phase 2).

transactions 테이블에서 집계하고, spend_profile_cache로 캐싱.
Redis 가용 시 Redis TTL 캐시도 사용.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.redis import cache_delete_pattern, cache_get, cache_set
from app.models.tables import SpendProfileCache, Transaction, User
from app.schemas.spend import (
    CategorySummary,
    SpendCategory,
    SpendProfile,
    TransactionIngest,
)


# ──────────────────────────────────────────────
#  거래 수집
# ──────────────────────────────────────────────

async def ingest_transaction(tx: TransactionIngest, session: AsyncSession) -> None:
    """거래 1건을 DB에 저장하고 캐시를 무효화."""
    # User가 없으면 자동 생성 (레거시 호환)
    result = await session.execute(select(User).where(User.user_id == tx.user_id))
    if not result.scalar_one_or_none():
        session.add(User(user_id=tx.user_id))
        await session.flush()

    db_tx = Transaction(
        transaction_id=tx.transaction_id,
        user_id=tx.user_id,
        amount=tx.amount,
        timestamp=tx.timestamp,
        merchant_id=tx.merchant_id,
        category=tx.category.value,
        channel=tx.channel,
        is_domestic=tx.is_domestic,
        memo=tx.memo,
    )
    session.add(db_tx)
    await session.commit()

    period = tx.timestamp.strftime("%Y-%m")
    await _invalidate_cache(tx.user_id, period)


async def ingest_batch(txs: list[TransactionIngest], session: AsyncSession) -> int:
    """거래 배치를 DB에 저장."""
    if not txs:
        return 0

    user_ids = {tx.user_id for tx in txs}
    for uid in user_ids:
        result = await session.execute(select(User).where(User.user_id == uid))
        if not result.scalar_one_or_none():
            session.add(User(user_id=uid))
    await session.flush()

    for tx in txs:
        db_tx = Transaction(
            transaction_id=tx.transaction_id,
            user_id=tx.user_id,
            amount=tx.amount,
            timestamp=tx.timestamp,
            merchant_id=tx.merchant_id,
            category=tx.category.value,
            channel=tx.channel,
            is_domestic=tx.is_domestic,
            memo=tx.memo,
        )
        session.add(db_tx)
    await session.commit()

    # 캐시 무효화
    periods = {tx.timestamp.strftime("%Y-%m") for tx in txs}
    for uid in user_ids:
        for period in periods:
            await _invalidate_cache(uid, period)

    return len(txs)


# ──────────────────────────────────────────────
#  프로필 조회
# ──────────────────────────────────────────────

async def get_profile(user_id: str, session: AsyncSession) -> SpendProfile | None:
    """소비 프로필 반환. Redis → DB 캐시 → 실시간 집계 순으로 조회."""
    cache_key = f"profile:{user_id}:summary"
    cached = await cache_get(cache_key)
    if cached:
        return SpendProfile(**cached)

    # DB에서 집계
    result = await session.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count().label("cnt"),
            func.avg(Transaction.amount).label("avg"),
            func.max(Transaction.amount).label("max_amt"),
        )
        .where(Transaction.user_id == user_id)
        .group_by(Transaction.category)
    )
    rows = result.all()
    if not rows:
        return None

    total_amount = sum(r.total for r in rows)
    tx_count = sum(r.cnt for r in rows)
    max_amount = max(r.max_amt for r in rows)

    breakdown = []
    top_cat = SpendCategory.OTHER
    top_total = 0.0
    for r in rows:
        cat = r.category if r.category in SpendCategory._value2member_map_ else "other"
        summary = CategorySummary(
            category=SpendCategory(cat),
            total_amount=r.total,
            tx_count=r.cnt,
            avg_amount=r.avg,
            pct_of_total=r.total / total_amount if total_amount > 0 else 0,
        )
        breakdown.append(summary)
        if r.total > top_total:
            top_total = r.total
            top_cat = SpendCategory(cat)

    # 피크 시간대
    hour_result = await session.execute(
        select(
            func.extract("hour", Transaction.timestamp).label("h"),
            func.count().label("cnt"),
        )
        .where(Transaction.user_id == user_id)
        .group_by(func.extract("hour", Transaction.timestamp))
        .order_by(func.count().desc())
        .limit(1)
    )
    peak_row = hour_result.first()
    peak_hour = int(peak_row.h) if peak_row else 0

    # 기간
    period_result = await session.execute(
        select(
            func.min(Transaction.timestamp).label("pstart"),
            func.max(Transaction.timestamp).label("pend"),
        ).where(Transaction.user_id == user_id)
    )
    period_row = period_result.first()

    profile = SpendProfile(
        user_id=user_id,
        total_tx_count=tx_count,
        total_amount=total_amount,
        avg_amount=total_amount / tx_count,
        max_amount=max_amount,
        peak_hour=peak_hour,
        top_category=top_cat,
        category_breakdown=sorted(breakdown, key=lambda x: x.total_amount, reverse=True),
        period_start=period_row.pstart if period_row else None,
        period_end=period_row.pend if period_row else None,
    )
    await cache_set(cache_key, profile.model_dump(), settings.CACHE_TTL_SPEND_PROFILE)
    return profile


async def get_trend(user_id: str, session: AsyncSession) -> dict[str, dict[str, float]]:
    """월별 카테고리 지출 추이."""
    cache_key = f"profile:{user_id}:trend"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await session.execute(
        select(
            func.to_char(Transaction.timestamp, "YYYY-MM").label("period"),
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .where(Transaction.user_id == user_id)
        .group_by(func.to_char(Transaction.timestamp, "YYYY-MM"), Transaction.category)
        .order_by(func.to_char(Transaction.timestamp, "YYYY-MM"))
    )
    rows = result.all()
    if not rows:
        return {}

    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        monthly[r.period][r.category] += r.total
        monthly[r.period]["_total"] += r.total

    data = {k: dict(v) for k, v in sorted(monthly.items())}
    await cache_set(cache_key, data, settings.CACHE_TTL_SPEND_PROFILE)
    return data


async def delete_user_data(user_id: str, session: AsyncSession) -> bool:
    """사용자 거래 데이터 및 캐시 삭제."""
    result = await session.execute(
        select(Transaction.id).where(Transaction.user_id == user_id).limit(1)
    )
    if not result.first():
        return False
    await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await session.execute(delete(SpendProfileCache).where(SpendProfileCache.user_id == user_id))
    await session.commit()
    await cache_delete_pattern(f"profile:{user_id}:*")
    return True


# ──────────────────────────────────────────────
#  내부 헬퍼
# ──────────────────────────────────────────────

async def get_transactions(user_id: str, session: AsyncSession, limit: int = 1000) -> list[TransactionIngest]:
    """거래 목록 반환 (ML 모델 피드용)."""
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        TransactionIngest(
            transaction_id=r.transaction_id,
            user_id=r.user_id,
            amount=r.amount,
            timestamp=r.timestamp,
            merchant_id=r.merchant_id,
            category=SpendCategory(r.category) if r.category in SpendCategory._value2member_map_ else SpendCategory.OTHER,
            channel=r.channel,
            is_domestic=r.is_domestic,
            memo=r.memo,
        )
        for r in rows
    ]


async def _invalidate_cache(user_id: str, period: str) -> None:
    await cache_delete_pattern(f"profile:{user_id}:*")
