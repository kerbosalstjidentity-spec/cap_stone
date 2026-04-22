from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.profile_store import profile_store

router = APIRouter()


class IngestRequest(BaseModel):
    user_id: str
    tx_id: str = ""
    amount: float = Field(..., ge=0.0)
    timestamp: str | None = None   # ISO 8601. None이면 현재 시각
    merchant_id: str = ""
    device_id: str = ""
    ip: str = ""
    is_foreign_ip: bool = False
    hour: int = Field(default=-1, ge=-1, le=23)


@router.post("/ingest", status_code=204)
def ingest(req: IngestRequest) -> None:
    profile_store.ingest(req.user_id, req.model_dump())


@router.get("/{user_id}")
def get_profile(user_id: str) -> dict[str, Any]:
    profile = profile_store.get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"프로파일 없음: {user_id}")
    return {
        "user_id": profile.user_id,
        "tx_count": profile.tx_count,
        "avg_amount": round(profile.avg_amount),
        "max_amount": profile.max_amount,
        "peak_hour": profile.peak_hour,
        "merchant_diversity": profile.merchant_diversity,
        "velocity": profile.velocity,
    }


@router.get("/{user_id}/velocity")
def get_velocity(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "velocity": {
            "1m": profile_store.get_velocity(user_id, 1),
            "5m": profile_store.get_velocity(user_id, 5),
            "15m": profile_store.get_velocity(user_id, 15),
        },
    }


@router.delete("/{user_id}", status_code=204)
def delete_profile(user_id: str) -> None:
    if not profile_store.delete(user_id):
        raise HTTPException(status_code=404, detail=f"프로파일 없음: {user_id}")
