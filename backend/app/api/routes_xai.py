"""XAI (Explainable AI) API — ML 예측 설명 엔드포인트."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.xai_engine import explain_overspend, explain_anomalies, explain_cluster

router = APIRouter(prefix="/v1/xai", tags=["xai"])


@router.get("/overspend/{user_id}")
async def xai_overspend(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """과소비 분류기 SHAP 기반 설명."""
    return await explain_overspend(user_id, session)


@router.get("/anomalies/{user_id}")
async def xai_anomalies(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """이상 거래 Feature 기여도 설명."""
    return await explain_anomalies(user_id, session)


@router.get("/cluster/{user_id}")
async def xai_cluster(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """K-Means 군집 귀속 설명."""
    return await explain_cluster(user_id, session)
