"""시나리오 검출률 집계 API (W5.5-#1).

블로그 12 §Track 2 — `scenario_generator` 가 합성한 4종 시나리오를
``FraudServiceManager.get_final_action`` 에 통과시키고 BLOCK/REVIEW/SOFT_REVIEW/PASS
분포를 집계해 ``detection_rate = (BLOCK + REVIEW) / total`` 로 반환한다.

신규 평가 로직 없음 — 라우터는 집계만 담당.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.fraud_service import FraudServiceManager
from app.services.scenario_generator import SCENARIO_TYPES, generate_all

router = APIRouter()


class ScenarioRunRequest(BaseModel):
    scenarios: list[str] = Field(
        default_factory=lambda: list(SCENARIO_TYPES),
        description="합성할 시나리오 키 (기본: 4종 전체)",
    )
    count: int = Field(default=100, ge=1, le=1000, description="시나리오당 트랜잭션 수")
    seed: int = Field(default=42, description="결정적 합성을 위한 시드")


def _aggregate(transactions: list[dict]) -> dict[str, Any]:
    counts = {"BLOCK": 0, "REVIEW": 0, "SOFT_REVIEW": 0, "PASS": 0}
    for tx in transactions:
        action = FraudServiceManager(tx).get_final_action()
        counts[action] = counts.get(action, 0) + 1
    total = len(transactions) or 1
    detected = counts["BLOCK"] + counts["REVIEW"]
    return {
        "total": len(transactions),
        **counts,
        "detection_rate": round(detected / total, 4),
    }


@router.post("/run")
def run(req: ScenarioRunRequest) -> dict[str, Any]:
    unknown = [s for s in req.scenarios if s not in SCENARIO_TYPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown scenarios: {unknown}. expected: {list(SCENARIO_TYPES)}",
        )
    bundles = generate_all(scenarios=req.scenarios, count=req.count, seed=req.seed)
    table = {name: _aggregate(txs) for name, txs in bundles.items()}
    overall_total = sum(row["total"] for row in table.values()) or 1
    overall_detected = sum(row["BLOCK"] + row["REVIEW"] for row in table.values())
    return {
        "count": req.count,
        "seed": req.seed,
        "results": table,
        "overall_detection_rate": round(overall_detected / overall_total, 4),
    }


@router.get("/types")
def list_types() -> dict[str, Any]:
    return {"scenarios": list(SCENARIO_TYPES)}
