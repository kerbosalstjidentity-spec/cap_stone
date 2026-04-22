"""소비 프로필 API — 거래 수집, 프로필 조회, 카테고리 집계 (DB 기반)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.spend import (
    SpendProfile,
    TransactionBatchIngest,
    TransactionIngest,
    TrendPoint,
)
from app.services.fraud_client import fetch_fraud_profile
from app.services.spend_profile_db import (
    delete_user_data,
    get_profile,
    get_trend,
    ingest_batch,
    ingest_transaction,
)

router = APIRouter(prefix="/v1/profile", tags=["profile"])


@router.post(
    "/ingest",
    status_code=201,
    summary="거래 단건 수집",
    description="사용자의 거래 1건을 수집하여 소비 프로필에 반영합니다.",
    response_description="수집 완료 확인",
)
async def ingest_transaction_endpoint(
    tx: TransactionIngest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await ingest_transaction(tx, session)
    return {"status": "ingested", "transaction_id": tx.transaction_id}


@router.post(
    "/ingest/batch",
    status_code=201,
    summary="거래 배치 수집",
    description="여러 건의 거래를 한 번에 수집합니다.",
    response_description="수집된 건수 반환",
)
async def ingest_batch_endpoint(
    batch: TransactionBatchIngest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    count = await ingest_batch(batch.transactions, session)
    return {"status": "ingested", "count": count}


@router.get(
    "/{user_id}",
    response_model=SpendProfile,
    summary="소비 프로필 조회",
    description="사용자의 전체 소비 프로필을 반환합니다. Redis → DB 캐시 → 실시간 집계 순으로 조회.",
    response_description="소비 프로필 전체",
)
async def get_profile_endpoint(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    profile = await get_profile(user_id, session)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return profile


@router.get(
    "/{user_id}/categories",
    summary="카테고리별 지출 집계",
    description="카테고리별 총액, 건수, 평균, 비중을 반환합니다.",
)
async def get_categories(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    profile = await get_profile(user_id, session)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return {"user_id": user_id, "categories": profile.category_breakdown}


@router.get(
    "/{user_id}/trend",
    summary="월별 지출 추이",
    description="월별 카테고리 지출 추이를 반환합니다.",
)
async def get_trend_endpoint(user_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    monthly = await get_trend(user_id, session)
    if not monthly:
        raise HTTPException(404, f"User {user_id} not found or no data")
    points = []
    for period, amounts in monthly.items():
        total = amounts.pop("_total", 0.0)
        points.append(TrendPoint(period=period, total_amount=total, category_amounts=amounts))
    return {"user_id": user_id, "trend": points}


@router.get(
    "/{user_id}/fraud",
    summary="fraud-service 사기 프로필 조회",
)
async def get_fraud_profile(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_profile(user_id, session)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    fraud_data = await fetch_fraud_profile(user_id)
    if fraud_data is None:
        raise HTTPException(
            503,
            detail={
                "error": "fraud-service unavailable",
                "message": "fraud-service(port 8010)에 연결할 수 없습니다.",
            },
        )
    return {"user_id": user_id, "fraud_profile": fraud_data}


@router.delete(
    "/{user_id}",
    summary="프로필 초기화",
    description="사용자의 모든 거래 이력과 프로필 데이터를 삭제합니다.",
)
async def delete_profile(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    deleted = await delete_user_data(user_id, session)
    if not deleted:
        raise HTTPException(404, f"User {user_id} not found")
    return {"status": "deleted", "user_id": user_id}
