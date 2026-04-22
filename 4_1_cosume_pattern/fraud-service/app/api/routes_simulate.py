from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.fraud_service import FraudServiceManager, SYSTEM_CONFIG
from app.services.rule_engine import rule_engine
from app.services.profile_store import profile_store

router = APIRouter()


class SimulateRequest(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    amount: float = Field(..., ge=0.0)
    user_id: str = ""
    hour: int = Field(default=-1, ge=-1, le=23)
    is_foreign_ip: bool = False
    ip: str = ""
    merchant_id: str = ""
    device_id: str = ""


class SimulateScenario(BaseModel):
    label: str
    score: float = Field(..., ge=0.0, le=1.0)
    amount: float = Field(..., ge=0.0)
    hour: int = Field(default=-1, ge=-1, le=23)
    is_foreign_ip: bool = False


class BatchSimulateRequest(BaseModel):
    scenarios: list[SimulateScenario]


def _evaluate_tx(tx: dict) -> dict[str, Any]:
    manager = FraudServiceManager(tx)
    profile = profile_store.get_profile(tx.get("user_id", ""))
    rule_results = rule_engine.evaluate_all(tx, profile)
    rule_action, rule_ids = rule_engine.get_strongest(rule_results)
    final_action = manager.get_final_action()
    return {
        "model_action": manager.get_model_action(),
        "rule_action": rule_action,
        "triggered_rules": [{"rule_id": r.rule_id, "action": r.action, "detail": r.detail} for r in rule_results],
        "final_action": final_action,
    }


@router.post("")
def simulate(req: SimulateRequest) -> dict[str, Any]:
    tx = req.model_dump()
    result = _evaluate_tx(tx)

    # what-if: score를 0.3으로 낮추면?
    tx_low_score = {**tx, "score": 0.3}
    what_if_low_score = _evaluate_tx(tx_low_score)["final_action"]

    # what-if: 금액을 50,000원으로 낮추면?
    tx_low_amount = {**tx, "amount": 50_000}
    what_if_low_amount = _evaluate_tx(tx_low_amount)["final_action"]

    # what-if: 해외 IP 없애면?
    tx_no_foreign = {**tx, "is_foreign_ip": False}
    what_if_no_foreign = _evaluate_tx(tx_no_foreign)["final_action"]

    return {
        **result,
        "input": {"score": req.score, "amount": req.amount, "hour": req.hour, "is_foreign_ip": req.is_foreign_ip},
        "what_if": {
            "if_score_0.3": what_if_low_score,
            "if_amount_50000": what_if_low_amount,
            "if_no_foreign_ip": what_if_no_foreign,
        },
    }


@router.post("/batch")
def simulate_batch(req: BatchSimulateRequest) -> dict[str, Any]:
    results = []
    for s in req.scenarios:
        tx = s.model_dump()
        result = _evaluate_tx(tx)
        results.append({"label": s.label, **result})
    return {"count": len(results), "results": results}


@router.get("/threshold-sweep")
def threshold_sweep(
    score: float = 0.7,
    amount: float = 500_000,
) -> dict[str, Any]:
    """
    BLOCK_THRESHOLD를 0.5~0.99 범위로 바꿔가며 해당 score/amount 조합의 final_action 변화를 반환.
    """
    thresholds = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99]
    original = SYSTEM_CONFIG["BLOCK_THRESHOLD"]
    sweep = []
    for t in thresholds:
        SYSTEM_CONFIG["BLOCK_THRESHOLD"] = t
        tx = {"score": score, "amount": amount}
        manager = FraudServiceManager(tx)
        sweep.append({"block_threshold": t, "model_action": manager.get_model_action()})
    SYSTEM_CONFIG["BLOCK_THRESHOLD"] = original
    return {"score": score, "amount": amount, "sweep": sweep}
