"""소비 프로필 API — 거래 수집, 프로필 조회, 카테고리 집계."""

from fastapi import APIRouter, HTTPException

from app.schemas.spend import (
    SpendProfile,
    TransactionBatchIngest,
    TransactionIngest,
    TrendPoint,
)
from app.services.spend_profile import profile_store

router = APIRouter(prefix="/v1/profile", tags=["profile"])


@router.post(
    "/ingest",
    status_code=201,
    summary="거래 단건 수집",
    description="사용자의 거래 1건을 수집하여 소비 프로필에 반영합니다. MCC 코드 또는 카테고리를 기반으로 분류됩니다.",
    response_description="수집 완료 확인",
)
async def ingest_transaction(tx: TransactionIngest) -> dict:
    profile_store.ingest(tx)
    return {"status": "ingested", "transaction_id": tx.transaction_id}


@router.post(
    "/ingest/batch",
    status_code=201,
    summary="거래 배치 수집",
    description="여러 건의 거래를 한 번에 수집합니다. Open Banking 연동 또는 초기 데이터 마이그레이션에 활용합니다.",
    response_description="수집된 건수 반환",
)
async def ingest_batch(batch: TransactionBatchIngest) -> dict:
    for tx in batch.transactions:
        profile_store.ingest(tx)
    return {"status": "ingested", "count": len(batch.transactions)}


@router.get(
    "/{user_id}",
    response_model=SpendProfile,
    summary="소비 프로필 조회",
    description="사용자의 전체 소비 프로필을 반환합니다. 총 지출, 평균 금액, 카테고리별 비중, 피크 시간대 등을 포함합니다.",
    response_description="소비 프로필 전체",
)
async def get_profile(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return profile


@router.get(
    "/{user_id}/categories",
    summary="카테고리별 지출 집계",
    description="카테고리(식비, 쇼핑, 교통 등)별 총액, 건수, 평균, 비중을 반환합니다.",
    response_description="카테고리 요약 목록",
)
async def get_categories(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return {"user_id": user_id, "categories": profile.category_breakdown}


@router.get(
    "/{user_id}/trend",
    summary="월별 지출 추이",
    description="월별 카테고리 지출 추이를 반환합니다. 프론트엔드 차트(라인/바)에 직접 활용 가능한 형태입니다.",
    response_description="월별 지출 시계열 데이터",
)
async def get_trend(user_id: str) -> dict:
    monthly = profile_store.get_trend(user_id)
    if not monthly:
        raise HTTPException(404, f"User {user_id} not found or no data")
    points = []
    for period, amounts in monthly.items():
        total = amounts.pop("_total", 0.0)
        points.append(TrendPoint(period=period, total_amount=total, category_amounts=amounts))
    return {"user_id": user_id, "trend": points}


@router.delete(
    "/{user_id}",
    summary="프로필 초기화",
    description="사용자의 모든 거래 이력과 프로필 데이터를 삭제합니다. 테스트/데모 초기화 용도로 사용합니다.",
    response_description="삭제 완료 확인",
)
async def delete_profile(user_id: str) -> dict:
    deleted = profile_store.delete_user(user_id)
    if not deleted:
        raise HTTPException(404, f"User {user_id} not found")
    return {"status": "deleted", "user_id": user_id}
