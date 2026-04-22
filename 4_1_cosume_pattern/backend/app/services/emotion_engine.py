"""감정×소비 분석 엔진 — 감정 태깅, 상관 분석, 충동 소비 예측."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tables import EmotionTag, Transaction

logger = logging.getLogger(__name__)

EMOTIONS = ["happy", "stressed", "bored", "reward", "impulse", "neutral"]
EMOTION_KR = {
    "happy": "기쁨", "stressed": "스트레스", "bored": "무료함",
    "reward": "보상심리", "impulse": "충동", "neutral": "평온",
}
CATEGORIES = [
    "food", "shopping", "transport", "entertainment", "education",
    "healthcare", "housing", "utilities", "finance", "travel", "other",
]
CATEGORY_KR = {
    "food": "식비", "shopping": "쇼핑", "transport": "교통",
    "entertainment": "여가", "education": "교육", "healthcare": "의료",
    "housing": "주거", "utilities": "공과금", "finance": "금융",
    "travel": "여행", "other": "기타",
}
DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 충동 소비 위험 시간대 가중치 (0~23시)
HOUR_RISK = {
    **{h: 0.2 for h in range(6, 11)},    # 아침 출근
    **{h: 0.1 for h in range(11, 17)},   # 낮
    **{h: 0.3 for h in range(17, 21)},   # 저녁 퇴근
    **{h: 0.4 for h in range(21, 24)},   # 밤
    **{h: 0.3 for h in range(0, 6)},     # 새벽
}
WEEKEND_BONUS = 0.1  # 주말 추가 가중치


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  감정 태깅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def upsert_emotion_tag(
    session: AsyncSession,
    user_id: str,
    transaction_id: str,
    emotion: str,
    intensity: int = 3,
    note: str = "",
) -> EmotionTag:
    """감정 태그 생성 또는 업데이트 (거래당 1개)."""
    stmt = select(EmotionTag).where(
        EmotionTag.user_id == user_id,
        EmotionTag.transaction_id == transaction_id,
    )
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()

    if tag:
        tag.emotion = emotion
        tag.intensity = intensity
        tag.note = note
    else:
        tag = EmotionTag(
            user_id=user_id,
            transaction_id=transaction_id,
            emotion=emotion,
            intensity=intensity,
            note=note,
        )
        session.add(tag)

    await session.flush()
    return tag


async def get_emotion_tags(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
) -> list[dict]:
    """사용자의 감정 태그 목록 (거래 정보 포함)."""
    stmt = (
        select(EmotionTag, Transaction)
        .join(Transaction, EmotionTag.transaction_id == Transaction.transaction_id)
        .where(EmotionTag.user_id == user_id)
        .order_by(Transaction.timestamp.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": tag.id,
            "user_id": tag.user_id,
            "transaction_id": tag.transaction_id,
            "emotion": tag.emotion,
            "emotion_kr": EMOTION_KR.get(tag.emotion, tag.emotion),
            "intensity": tag.intensity,
            "note": tag.note,
            "created_at": tag.created_at,
            "amount": tx.amount,
            "category": tx.category,
            "category_kr": CATEGORY_KR.get(tx.category, tx.category),
            "timestamp": tx.timestamp,
        }
        for tag, tx in rows
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  감정×카테고리 상관 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def compute_correlation(session: AsyncSession, user_id: str) -> dict:
    """감정별×카테고리별 평균 지출 및 전체 평균 대비 배수."""
    stmt = (
        select(
            EmotionTag.emotion,
            Transaction.category,
            func.avg(Transaction.amount).label("avg_amount"),
            func.count().label("count"),
            func.sum(Transaction.amount).label("total"),
        )
        .join(Transaction, EmotionTag.transaction_id == Transaction.transaction_id)
        .where(EmotionTag.user_id == user_id)
        .group_by(EmotionTag.emotion, Transaction.category)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # 전체 평균 (감정 무관)
    overall_stmt = select(func.avg(Transaction.amount)).where(Transaction.user_id == user_id)
    overall_avg = (await session.execute(overall_stmt)).scalar() or 1.0

    correlations = [
        {
            "emotion": row.emotion,
            "emotion_kr": EMOTION_KR.get(row.emotion, row.emotion),
            "category": row.category,
            "category_kr": CATEGORY_KR.get(row.category, row.category),
            "avg_amount": round(float(row.avg_amount), 2),
            "count": row.count,
            "total_amount": round(float(row.total), 2),
            "multiplier": round(float(row.avg_amount) / float(overall_avg), 2),
        }
        for row in rows
    ]

    return {"user_id": user_id, "correlations": correlations, "overall_avg": round(float(overall_avg), 2)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  히트맵 데이터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def compute_heatmap(session: AsyncSession, user_id: str) -> dict:
    """6(감정)×11(카테고리) 히트맵 데이터."""
    corr = await compute_correlation(session, user_id)
    data: dict[str, dict[str, dict]] = {}
    for item in corr["correlations"]:
        em = item["emotion"]
        cat = item["category"]
        if em not in data:
            data[em] = {}
        data[em][cat] = item

    # 최대값 (정규화용)
    max_val = max(
        (item["avg_amount"] for item in corr["correlations"]),
        default=1.0,
    )

    rows = []
    for emotion in EMOTIONS:
        cells = []
        for cat in CATEGORIES:
            item = data.get(emotion, {}).get(cat, {})
            raw = item.get("avg_amount", 0.0)
            cells.append({
                "category": cat,
                "category_kr": CATEGORY_KR.get(cat, cat),
                "value": round(raw / max_val, 4) if max_val > 0 else 0.0,
                "raw_avg": raw,
                "count": item.get("count", 0),
            })
        rows.append({
            "emotion": emotion,
            "emotion_kr": EMOTION_KR.get(emotion, emotion),
            "cells": cells,
        })

    return {"user_id": user_id, "rows": rows, "max_value": round(max_val, 2)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  충동 소비 위험도 예측
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def predict_impulse_risk(session: AsyncSession, user_id: str) -> dict:
    """현재 시간대 + 최근 감정 이력으로 충동 소비 위험도 계산."""
    now = datetime.utcnow()
    hour = now.hour
    weekday = now.weekday()  # 0=월 ~ 6=일
    is_weekend = weekday >= 5

    # 최근 24시간 감정 이력
    since = now - timedelta(hours=24)
    stmt = (
        select(EmotionTag)
        .join(Transaction, EmotionTag.transaction_id == Transaction.transaction_id)
        .where(EmotionTag.user_id == user_id, Transaction.timestamp >= since)
        .order_by(Transaction.timestamp.desc())
    )
    result = await session.execute(stmt)
    recent_tags = list(result.scalars().all())

    risk_factors = []
    score = 0.0

    # 1. 시간대 위험
    hour_weight = HOUR_RISK.get(hour, 0.1)
    score += hour_weight
    if hour_weight >= 0.3:
        risk_factors.append({
            "factor": "high_risk_hour",
            "weight": hour_weight,
            "description": f"현재 시간({hour}시)은 충동 소비가 잦은 시간대입니다.",
        })

    # 2. 주말 보너스
    if is_weekend:
        score += WEEKEND_BONUS
        risk_factors.append({
            "factor": "weekend",
            "weight": WEEKEND_BONUS,
            "description": "주말에는 평일 대비 충동 소비가 증가하는 경향이 있습니다.",
        })

    # 3. 최근 스트레스/충동 감정 태그
    stress_tags = [t for t in recent_tags if t.emotion in ("stressed", "impulse")]
    if stress_tags:
        intensity_avg = sum(t.intensity for t in stress_tags) / len(stress_tags)
        stress_weight = min(0.3, len(stress_tags) * 0.08) * (intensity_avg / 5)
        score += stress_weight
        risk_factors.append({
            "factor": "recent_stress",
            "weight": round(stress_weight, 3),
            "description": f"최근 24시간 내 스트레스/충동 태그 {len(stress_tags)}건이 기록되었습니다.",
        })

    # 4. 저녁+스트레스 복합
    if hour >= 18 and stress_tags:
        combo_weight = 0.15
        score += combo_weight
        risk_factors.append({
            "factor": "evening_stress_combo",
            "weight": combo_weight,
            "description": "저녁 시간대 + 스트레스 상태의 복합 위험입니다.",
        })

    score = min(score, 1.0)

    if score >= 0.75:
        level, msg = "danger", "지금은 큰 지출을 자제하세요. 충동 소비 위험이 매우 높습니다."
    elif score >= 0.55:
        level, msg = "warning", "소비 전 한 번 더 생각해보세요. 충동 소비 위험이 높습니다."
    elif score >= 0.35:
        level, msg = "caution", "소비 습관에 주의가 필요한 시간대입니다."
    else:
        level, msg = "safe", "현재 충동 소비 위험이 낮습니다."

    return {
        "user_id": user_id,
        "risk_score": round(score, 4),
        "risk_level": level,
        "warning_message": msg,
        "risk_factors": risk_factors,
        "current_hour": hour,
        "current_day": DAY_KR[weekday],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 인사이트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_insights(session: AsyncSession, user_id: str) -> dict:
    """감정별 소비 패턴 인사이트 — 배수가 높은 조합 강조."""
    corr = await compute_correlation(session, user_id)
    insights = []

    for item in sorted(corr["correlations"], key=lambda x: x["multiplier"], reverse=True):
        mult = item["multiplier"]
        if mult < 1.5:
            continue
        if mult >= 2.5:
            severity = "danger"
        elif mult >= 2.0:
            severity = "warning"
        else:
            severity = "info"

        text = (
            f"{item['emotion_kr']} 상태일 때 {item['category_kr']} 지출이 "
            f"평소 대비 {mult:.1f}배 증가하는 경향이 있습니다."
        )
        insights.append({
            "insight_text": text,
            "emotion": item["emotion"],
            "emotion_kr": item["emotion_kr"],
            "related_category": item["category"],
            "category_kr": item["category_kr"],
            "multiplier": mult,
            "severity": severity,
        })

        if len(insights) >= 6:
            break

    return {"user_id": user_id, "insights": insights}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  알림 연동
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_and_notify(session: AsyncSession, user_id: str) -> None:
    """충동 위험이 threshold 이상이면 실시간 알림 발송."""
    try:
        risk = await predict_impulse_risk(session, user_id)
        if risk["risk_score"] >= settings.EMOTION_RISK_THRESHOLD:
            from app.services.notification_service import create_and_push
            await create_and_push(
                session=session,
                user_id=user_id,
                event_type="emotion_risk",
                title="충동 소비 주의",
                body=risk["warning_message"],
                metadata={"risk_score": risk["risk_score"], "risk_level": risk["risk_level"]},
            )
    except Exception as e:
        logger.warning("[Emotion] check_and_notify error: %s", e)
