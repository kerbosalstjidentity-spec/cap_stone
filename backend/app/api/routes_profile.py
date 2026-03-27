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


@router.post("/ingest", status_code=201)
async def ingest_transaction(tx: TransactionIngest) -> dict:
    profile_store.ingest(tx)
    return {"status": "ingested", "transaction_id": tx.transaction_id}


@router.post("/ingest/batch", status_code=201)
async def ingest_batch(batch: TransactionBatchIngest) -> dict:
    for tx in batch.transactions:
        profile_store.ingest(tx)
    return {"status": "ingested", "count": len(batch.transactions)}


@router.get("/{user_id}", response_model=SpendProfile)
async def get_profile(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return profile


@router.get("/{user_id}/categories")
async def get_categories(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")
    return {"user_id": user_id, "categories": profile.category_breakdown}


@router.get("/{user_id}/trend")
async def get_trend(user_id: str) -> dict:
    monthly = profile_store.get_trend(user_id)
    if not monthly:
        raise HTTPException(404, f"User {user_id} not found or no data")
    points = []
    for period, amounts in monthly.items():
        total = amounts.pop("_total", 0.0)
        points.append(TrendPoint(period=period, total_amount=total, category_amounts=amounts))
    return {"user_id": user_id, "trend": points}


@router.delete("/{user_id}")
async def delete_profile(user_id: str) -> dict:
    deleted = profile_store.delete_user(user_id)
    if not deleted:
        raise HTTPException(404, f"User {user_id} not found")
    return {"status": "deleted", "user_id": user_id}
