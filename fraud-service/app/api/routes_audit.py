"""
Layer 4 — Blockchain 감사 추적 API 엔드포인트.

/v1/audit/chain/status       → 체인 상태 (Merkle root 포함)
/v1/audit/chain/verify       → 전체 무결성 검증
/v1/audit/chain/verify-range → 범위 검증
/v1/audit/chain/merkle-root  → Merkle root 조회
/v1/audit/chain/stats        → 통계
/v1/audit/block/{index}      → 블록 전체 조회
/v1/audit/block/{index}/onchain → 온체인 레코드만 조회
/v1/audit/block/{index}/verify-offchain → 오프체인 무결성 검증
/v1/audit/search             → 거래 ID 검색
/v1/audit/search/user        → 사용자 ID 검색
/v1/audit/search/action      → 액션 타입 검색
/v1/audit/search/time-range  → 시간 범위 검색
/v1/audit/recent             → 최근 블록 목록
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.blockchain_audit import audit_chain

router = APIRouter()


@router.get("/chain/status")
def chain_status() -> dict[str, Any]:
    """체인 길이, 최신 해시, 타임스탬프, Merkle root."""
    return audit_chain.status()


@router.get("/chain/verify")
def chain_verify() -> dict[str, Any]:
    """전체 해시 체인 무결성 검증 (Merkle leaf 포함)."""
    return audit_chain.verify()


@router.get("/chain/verify-range")
def chain_verify_range(
    start: int = Query(..., ge=0, description="시작 블록 인덱스"),
    end: int = Query(..., ge=0, description="종료 블록 인덱스"),
) -> dict[str, Any]:
    """특정 범위의 블록 무결성 검증."""
    return audit_chain.verify_range(start, end)


@router.get("/chain/merkle-root")
def chain_merkle_root() -> dict[str, Any]:
    """현재 체인의 Merkle root 반환."""
    return {"merkle_root": audit_chain.get_merkle_root()}


@router.get("/chain/stats")
def chain_stats() -> dict[str, Any]:
    """체인 통계: 액션별 블록 수, 평균 점수 등."""
    return audit_chain.stats()


@router.get("/block/{index}")
def get_block(index: int) -> dict[str, Any]:
    """인덱스로 블록 전체 조회 (온체인 + 오프체인)."""
    block = audit_chain.get_block(index)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block {index} not found")
    return block


@router.get("/block/{index}/onchain")
def get_block_onchain(index: int) -> dict[str, Any]:
    """인덱스로 온체인 레코드만 조회 (해시, Merkle leaf, 타임스탬프)."""
    record = audit_chain.get_onchain(index)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Block {index} not found")
    return record


@router.get("/block/{index}/verify-offchain")
def verify_block_offchain(index: int) -> dict[str, Any]:
    """특정 블록의 오프체인 데이터 무결성 검증."""
    return audit_chain.verify_offchain_integrity(index)


@router.get("/search")
def search_by_tx(tx_id: str = Query(..., description="거래 ID")) -> dict[str, Any]:
    """거래 ID로 감사 블록 검색."""
    results = audit_chain.search(tx_id)
    return {"tx_id": tx_id, "count": len(results), "blocks": results}


@router.get("/search/user")
def search_by_user(user_id: str = Query(..., description="사용자 ID")) -> dict[str, Any]:
    """사용자 ID로 감사 블록 검색."""
    results = audit_chain.search_by_user(user_id)
    return {"user_id": user_id, "count": len(results), "blocks": results}


@router.get("/search/action")
def search_by_action(action: str = Query(..., description="액션 타입 (PASS/REVIEW/BLOCK 등)")) -> dict[str, Any]:
    """액션 타입으로 감사 블록 검색."""
    results = audit_chain.search_by_action(action)
    return {"action": action.upper(), "count": len(results), "blocks": results}


@router.get("/search/time-range")
def search_by_time_range(
    start: str = Query(..., description="시작 시각 (ISO 8601)"),
    end: str = Query(..., description="종료 시각 (ISO 8601)"),
) -> dict[str, Any]:
    """시간 범위로 감사 블록 검색."""
    results = audit_chain.search_by_time_range(start, end)
    return {"start": start, "end": end, "count": len(results), "blocks": results}


@router.get("/recent")
def recent_blocks(n: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    """최근 n개 블록 (최신순)."""
    blocks = audit_chain.tail(n)
    return {"count": len(blocks), "blocks": blocks}
