from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.fraud_service import FraudServiceManager, generate_risk_leakage_report
from app.services.stats_collector import stats_collector
from app.services import audit_logger
from app.services.blockchain_audit import audit_chain
from app.services.behavioral_signals import analyze_signals

router = APIRouter()

# Step-up Auth 대기 중인 tx 상태 저장: tx_id → {"score", "amount", "reason_code", "status"}
_stepup_store: dict[str, dict] = {}
_stepup_lock = threading.Lock()


class FraudEvaluateRequest(BaseModel):
    tx_id: str = Field(..., description="트랜잭션 ID")
    score: float = Field(..., ge=0.0, le=1.0, description="모델 산출 확률")
    amount: float = Field(..., ge=0.0, description="거래 금액 (원)")
    reason_code: str = Field(default="", description="모델 reason_code (/v1/score 응답값)")
    user_id: str = Field(default="", description="사용자 ID (Rule Engine 프로파일 조회용)")
    hour: int = Field(default=-1, ge=-1, le=23, description="거래 시각 (0~23). -1=미지정")
    is_foreign_ip: bool = Field(default=False)
    ip: str = Field(default="")
    merchant_id: str = Field(default="")
    device_id: str = Field(default="")
    fcm_token: str = Field(default="", description="FCM 디바이스 토큰 (Step-up 푸시용)")
    signals: dict | None = Field(default=None, description="Layer 1 행동 시그널 (브라우저/앱 SDK)")


class StepUpResultRequest(BaseModel):
    tx_id: str = Field(..., description="Step-up Auth 대상 트랜잭션 ID")
    approved: bool = Field(..., description="사용자 승인 여부")


def _evaluate_one(tx_data: dict) -> dict[str, Any]:
    """단건 평가 공통 로직 — evaluate / batch 둘 다 재사용."""
    # Layer 1: 행동 시그널 리스크 분석
    signal_result = analyze_signals(tx_data.get("signals"))
    manager = FraudServiceManager(tx_data)
    model_action = manager.get_model_action()
    rule_action, rule_id = manager.get_rule_action()
    final_action = manager.get_final_action()
    step_up = manager.trigger_step_up_auth()

    triggered = rule_id.split(",") if rule_id else []
    stats_collector.record(tx_data.get("tx_id", ""), final_action, triggered,
                           float(tx_data.get("score", 0)), float(tx_data.get("amount", 0)))
    audit_logger.write(
        tx_id=tx_data.get("tx_id", ""),
        user_id=tx_data.get("user_id", ""),
        final_action=final_action,
        rule_id=rule_id or "",
        score=float(tx_data.get("score", 0)),
        amount=float(tx_data.get("amount", 0)),
        reason_code=tx_data.get("reason_code", ""),
    )
    # Layer 4: Blockchain 감사 체인에 블록 추가
    audit_chain.append(
        transaction_id=tx_data.get("tx_id", ""),
        user_id=tx_data.get("user_id", ""),
        action=final_action,
        score=float(tx_data.get("score", 0)),
        rule_ids=triggered,
        reason_code=tx_data.get("reason_code", ""),
        amount=float(tx_data.get("amount", 0)),
    )

    if step_up.get("push_sent") and final_action in ("REVIEW", "SOFT_REVIEW"):
        with _stepup_lock:
            _stepup_store[tx_data["tx_id"]] = {
                "score": tx_data.get("score"),
                "amount": tx_data.get("amount"),
                "reason_code": tx_data.get("reason_code", ""),
                "pre_action": final_action,
                "status": "pending",
            }

    return {
        "tx_id": tx_data.get("tx_id"),
        "model_action": model_action,
        "rule_action": rule_action,
        "rule_id": rule_id or None,
        "final_action": final_action,
        "admin_routing": manager.get_admin_routing(),
        "user_message": manager.get_user_trust_message(),
        "step_up_auth": step_up,
        "audit": manager.get_audit(tx_data.get("reason_code", "")),
        "signal_analysis": {
            "risk_score": signal_result.risk_score,
            "flags": signal_result.flags,
        } if signal_result.flags else None,
    }


@router.post("/evaluate")
def evaluate_fraud(req: FraudEvaluateRequest) -> dict[str, Any]:
    return _evaluate_one(req.model_dump())


class BatchEvaluateRequest(BaseModel):
    transactions: list[FraudEvaluateRequest] = Field(..., min_length=1, max_length=500)


@router.post("/evaluate/batch")
def evaluate_batch(req: BatchEvaluateRequest) -> dict[str, Any]:
    results = [_evaluate_one(tx.model_dump()) for tx in req.transactions]
    action_counts: dict[str, int] = {}
    for r in results:
        action_counts[r["final_action"]] = action_counts.get(r["final_action"], 0) + 1
    return {
        "count": len(results),
        "action_summary": action_counts,
        "results": results,
    }


@router.post("/auth/step-up/result")
def step_up_result(req: StepUpResultRequest) -> dict[str, Any]:
    with _stepup_lock:
        entry = _stepup_store.get(req.tx_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Step-up 대기 tx 없음: {req.tx_id}")
    if entry["status"] != "pending":
        return {"tx_id": req.tx_id, "already_resolved": True, "final_action": entry.get("resolved_action")}

    if req.approved:
        final_action = "PASS"
        user_message = {
            "status": "Secure",
            "message": f"{int(entry['amount']):,}원 결제가 본인 확인 후 승인되었습니다.",
        }
    else:
        final_action = "BLOCK"
        user_message = {
            "status": "Blocked",
            "message": f"{int(entry['amount']):,}원 결제가 본인 거절로 차단되었습니다.",
        }

    with _stepup_lock:
        entry["status"] = "resolved"
        entry["resolved_action"] = final_action

    return {
        "tx_id": req.tx_id,
        "approved": req.approved,
        "pre_action": entry["pre_action"],
        "final_action": final_action,
        "user_message": user_message,
    }


@router.get("/auth/step-up/status/{tx_id}")
def step_up_status(tx_id: str) -> dict[str, Any]:
    with _stepup_lock:
        entry = _stepup_store.get(tx_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Step-up 대기 tx 없음: {tx_id}")
    return {"tx_id": tx_id, **entry}


@router.get("/risk-leakage-report")
def risk_leakage_report(total_processed_amount: float = Query(..., ge=0.0)) -> dict[str, Any]:
    try:
        report = generate_risk_leakage_report(total_processed_amount)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report
