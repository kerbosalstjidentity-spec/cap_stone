"""
Layer 4 — Blockchain 감사 추적 API 엔드포인트.

/v1/audit/chain/status   → 체인 상태
/v1/audit/chain/verify   → 무결성 검증
/v1/audit/block/{index}  → 블록 조회
/v1/audit/search         → 거래 ID 검색
/v1/audit/recent         → 최근 블록 목록
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.blockchain_audit import audit_chain

router = APIRouter()


@router.get("/chain/status")
def chain_status() -> dict[str, Any]:
    """체인 길이, 최신 해시, 타임스탬프."""
    return audit_chain.status()


@router.get("/chain/verify")
def chain_verify() -> dict[str, Any]:
    """전체 해시 체인 무결성 검증."""
    return audit_chain.verify()


@router.get("/block/{index}")
def get_block(index: int) -> dict[str, Any]:
    """인덱스로 블록 조회."""
    block = audit_chain.get_block(index)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block {index} not found")
    return block


@router.get("/search")
def search_by_tx(tx_id: str = Query(..., description="거래 ID")) -> dict[str, Any]:
    """거래 ID로 감사 블록 검색."""
    results = audit_chain.search(tx_id)
    return {"tx_id": tx_id, "count": len(results), "blocks": results}


@router.get("/recent")
def recent_blocks(n: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    """최근 n개 블록 (최신순)."""
    blocks = audit_chain.tail(n)
    return {"count": len(blocks), "blocks": blocks}
