"""감정×소비 분석 API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.tables import Transaction
from app.schemas.emotion import EmotionTagCreate
from app.services.emotion_engine import (
    upsert_emotion_tag,
    get_emotion_tags,
    compute_correlation,
    compute_heatmap,
    predict_impulse_risk,
    get_insights,
    check_and_notify,
)

router = APIRouter(prefix="/v1/emotion", tags=["emotion"])


@router.post("/tag")
async def tag_emotion(
    body: EmotionTagCreate,
    session: AsyncSession = Depends(get_session),
):
    """거래에 감정 태깅."""
    tag = await upsert_emotion_tag(
        session=session,
        user_id=body.user_id,
        transaction_id=body.transaction_id,
        emotion=body.emotion,
        intensity=body.intensity,
        note=body.note,
    )
    await session.commit()

    # 충동 위험 체크 → 알림
    await check_and_notify(session, body.user_id)

    return {
        "id": tag.id,
        "user_id": tag.user_id,
        "transaction_id": tag.transaction_id,
        "emotion": tag.emotion,
        "intensity": tag.intensity,
    }


@router.get("/tags/{user_id}")
async def list_emotion_tags(
    user_id: str,
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_session),
):
    """사용자 감정 태그 목록 (거래 정보 포함)."""
    tags = await get_emotion_tags(session, user_id, limit)
    return {"user_id": user_id, "tags": tags, "count": len(tags)}


@router.get("/correlation/{user_id}")
async def emotion_correlation(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """감정×카테고리 상관 매트릭스."""
    return await compute_correlation(session, user_id)


@router.get("/heatmap/{user_id}")
async def emotion_heatmap(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """감정×카테고리 히트맵 데이터."""
    return await compute_heatmap(session, user_id)


@router.get("/impulse-risk/{user_id}")
async def impulse_risk(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """현재 충동 소비 위험도."""
    return await predict_impulse_risk(session, user_id)


@router.get("/insights/{user_id}")
async def emotion_insights(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """감정 기반 소비 인사이트."""
    return await get_insights(session, user_id)


@router.get("/recent-transactions/{user_id}")
async def recent_transactions(
    user_id: str,
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_session),
):
    """최근 거래 목록 (감정 태깅용)."""
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.timestamp.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    txs = result.scalars().all()
    return {
        "transactions": [
            {
                "transaction_id": tx.transaction_id,
                "amount": float(tx.amount),
                "category": tx.category,
                "merchant_id": tx.merchant_id,
                "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
            }
            for tx in txs
        ],
        "count": len(txs),
    }
