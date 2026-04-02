"""
Layer 5 — ABE 암호화 사기 인텔리전스 공유 API.

POST /v1/intelligence/publish  → 패턴 게시
GET  /v1/intelligence/query    → 패턴 조회 (접근 정책 기반 필터링)
GET  /v1/intelligence/stats    → 저장소 통계
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.services.intelligence_store import intelligence_store
from app.services.abe_engine import AttributeToken

router = APIRouter()


class PublishRequest(BaseModel):
    publisher_institution: str = Field(..., description="게시 기관 ID")
    pattern_type: str = Field(..., description="패턴 유형: BLACKLIST | PATTERN | SIGNATURE | METRIC")
    summary: str = Field(..., description="공개 요약")
    access_policy: str = Field(..., description="CP-ABE 접근 구조식")
    detail: dict[str, Any] = Field(..., description="정책 만족 시 공개되는 상세 정보")
    tags: list[str] = Field(default_factory=list, description="검색용 태그")


@router.post("/publish")
def publish_intelligence(req: PublishRequest) -> dict[str, Any]:
    """새 인텔리전스 패턴을 게시한다."""
    entry = intelligence_store.publish(
        publisher_institution=req.publisher_institution,
        pattern_type=req.pattern_type,
        summary=req.summary,
        access_policy=req.access_policy,
        detail=req.detail,
        tags=req.tags,
    )
    return {
        "status": "published",
        "entry_id": entry.entry_id,
        "published_at": entry.published_at,
    }


@router.get("/query")
def query_intelligence(
    request: Request,
    pattern_type: str | None = Query(default=None, description="패턴 유형 필터"),
    tag: str | None = Query(default=None, description="태그 필터"),
) -> dict[str, Any]:
    """인텔리전스 패턴을 조회한다. 접근 정책에 따라 detail 필터링."""
    # request.state에서 ABE 속성 가져오기 (미들웨어에서 설정)
    attrs = getattr(request.state, "abe_attrs", {})
    if isinstance(attrs, dict):
        user_attrs = {f"{k}:{v}" for k, v in attrs.items()}
    else:
        user_attrs = set()

    results = intelligence_store.query(user_attrs, pattern_type, tag)
    accessible = sum(1 for r in results if r["has_access"])
    return {
        "total": len(results),
        "accessible": accessible,
        "entries": results,
    }


@router.get("/stats")
def intelligence_stats() -> dict[str, Any]:
    """저장소 통계."""
    return {"total_entries": intelligence_store.count()}
