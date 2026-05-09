from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.fraud_service import FraudServiceManager, generate_risk_leakage_report
from app.services.graph_features import extract_all as extract_graph_features
from app.services.graph_store import graph_store
from app.services.policy_merge import (
    apply_fraud_type_threshold,
    classify_fraud_type,
    fraud_type_label_ko,
)
from app.services.feedback_store import feedback_store, precision_recall_summary
from app.services.profile_store import profile_store
from app.services.stats_collector import stats_collector
from app.services import audit_logger
from app.services.blockchain_audit import audit_chain
from app.services.behavioral_signals import analyze_signals
# W2-#2: step-up 대기 상태를 외부 stepup_store(Redis hash)로 이관
from app.services import stepup_store

router = APIRouter()


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
    receiver_id: str = Field(default="", description="송금 수취자 ID (W6.5-#1 그래프 store)")
    nameDest: str = Field(default="", description="PaySim 호환 수취자 이름 — receiver_id 미지정 시 fallback")
    signals: dict | None = Field(default=None, description="Layer 1 행동 시그널 (브라우저/앱 SDK)")
    signal_signature: str = Field(default="", description="signals HMAC-SHA256 서명 (hex, W1-#6)")
    signal_timestamp: int = Field(default=0, description="signals 서명 타임스탬프 (epoch s, ±300s 허용)")


class StepUpResultRequest(BaseModel):
    tx_id: str = Field(..., description="Step-up Auth 대상 트랜잭션 ID")
    approved: bool = Field(..., description="사용자 승인 여부")


def _evaluate_one(tx_data: dict) -> dict[str, Any]:
    """단건 평가 공통 로직 — evaluate / batch 둘 다 재사용."""
    # W7.5-#6: SLO 대시보드용 latency 측정 시작
    _t0 = time.perf_counter()
    # Layer 1: 행동 시그널 리스크 분석 (W1-#6 HMAC 서명 검증 + 서버 IP 보강)
    server_ctx = {
        "ip": tx_data.get("ip", ""),
        "is_tor": False,  # TODO: IP 평판 DB 조회 (W8-#2 외부 위협 인텔)
    } if tx_data.get("ip") else None
    signal_result = analyze_signals(
        tx_data.get("signals"),
        signature=tx_data.get("signal_signature") or None,
        timestamp=tx_data.get("signal_timestamp") or None,
        server_context=server_ctx,
    )
    # W6.5-#2: 그래프 피처 — store 적재 *전* 시점에서 과거 컨텍스트 계산.
    # 본 평가의 결과로 사용은 W6.5-#3/#4 (MoneyMuleRule, LayeringRule) 에서.
    graph_feats = extract_graph_features(tx_data)
    # tx_data 에 합류해 룰엔진이 활용할 수 있도록 함 (룰은 tx dict 만 받음)
    tx_data = {**tx_data, "graph_features": graph_feats}

    manager = FraudServiceManager(tx_data)
    model_action = manager.get_model_action()
    rule_action, rule_id = manager.get_rule_action()
    final_action = manager.get_final_action()
    step_up = manager.trigger_step_up_auth()

    triggered = rule_id.split(",") if rule_id else []
    # W5.5-#5: 룰 발동 패턴 → 사기 유형 라벨
    fraud_type = classify_fraud_type(triggered)

    # W6.5-#6: fraud_type 별 차등 임계값 적용 — 룰 시그널 강한 유형은 낮은
    # score 에서도 BLOCK 으로 승격 (false-negative 감소).
    final_action = apply_fraud_type_threshold(
        final_action,
        score=float(tx_data.get("score", 0.0) or 0.0),
        fraud_type=fraud_type,
    )

    # W5.5-#8: 평가 직후 profile_store 갱신 — velocity/avg_amount 룰이 다음 거래에서
    # 발동할 수 있도록 한다. 이전엔 외부 호출자가 별도로 /v1/profile/ingest 를
    # 부르지 않으면 VelocityRule/SplitTransactionRule 등이 영구히 비활성이었음.
    user_id_for_ingest = tx_data.get("user_id", "")
    if user_id_for_ingest:
        try:
            profile_store.ingest(user_id_for_ingest, tx_data)
        except Exception:
            # ingest 실패는 평가 결과에 영향 주지 않도록 swallow
            pass

    # W6.5-#1: 송금 그래프 store 적재 — sender/receiver 모두 있는 경우에만
    # (PaySim TRANSFER/CASH_OUT 등). graph_features (W6.5-#2) 가 다음 거래
    # 평가 시 fan-in / pass-through ratio 등을 즉시 활용 가능.
    receiver = tx_data.get("nameDest") or tx_data.get("receiver_id") or ""
    if user_id_for_ingest and receiver:
        try:
            graph_store.record(
                sender=user_id_for_ingest,
                receiver=str(receiver),
                amount=float(tx_data.get("amount", 0) or 0),
                tx_id=str(tx_data.get("tx_id", "") or ""),
            )
        except Exception:
            pass
    _latency_ms = (time.perf_counter() - _t0) * 1000.0
    stats_collector.record(
        tx_data.get("tx_id", ""), final_action, triggered,
        float(tx_data.get("score", 0)), float(tx_data.get("amount", 0)),
        latency_ms=_latency_ms,
        scenario_label=tx_data.get("scenario_label") or None,
        expected_action=tx_data.get("expected_action") or None,
    )
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
        stepup_store.set_pending(tx_data["tx_id"], {
            "score": tx_data.get("score"),
            "amount": tx_data.get("amount"),
            "reason_code": tx_data.get("reason_code", ""),
            "pre_action": final_action,
            "status": "pending",
        })

    return {
        "tx_id": tx_data.get("tx_id"),
        "model_action": model_action,
        "rule_action": rule_action,
        "rule_id": rule_id or None,
        "final_action": final_action,
        "fraud_type": fraud_type,
        "fraud_type_label": fraud_type_label_ko(fraud_type),
        "expected_loss": round(manager.get_expected_loss(), 2),  # W6.5-#5
        "admin_routing": manager.get_admin_routing(),
        "user_message": manager.get_user_trust_message(),
        "step_up_auth": step_up,
        "audit": manager.get_audit(tx_data.get("reason_code", "")),
        "signal_analysis": {
            "risk_score": signal_result.risk_score,
            "flags": signal_result.flags,
        } if signal_result.flags else None,
        "graph_features": graph_feats,
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
    entry = stepup_store.get(req.tx_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Step-up 대기 tx 없음: {req.tx_id}")
    if entry.get("status") != "pending":
        return {"tx_id": req.tx_id, "already_resolved": True, "final_action": entry.get("resolved_action")}

    amount = float(entry.get("amount", 0))
    if req.approved:
        final_action = "PASS"
        user_message = {
            "status": "Secure",
            "message": f"{int(amount):,}원 결제가 본인 확인 후 승인되었습니다.",
        }
    else:
        final_action = "BLOCK"
        user_message = {
            "status": "Blocked",
            "message": f"{int(amount):,}원 결제가 본인 거절로 차단되었습니다.",
        }

    stepup_store.update_status(req.tx_id, "resolved", resolved_action=final_action)

    return {
        "tx_id": req.tx_id,
        "approved": req.approved,
        "pre_action": entry.get("pre_action"),
        "final_action": final_action,
        "user_message": user_message,
    }


@router.get("/auth/step-up/status/{tx_id}")
def step_up_status(tx_id: str) -> dict[str, Any]:
    entry = stepup_store.get(tx_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Step-up 대기 tx 없음: {tx_id}")
    return {"tx_id": tx_id, **entry}


class ChargebackFeedbackRequest(BaseModel):
    tx_id: str = Field(..., description="chargeback 대상 트랜잭션 ID")
    user_id: str = Field(default="", description="피해 사용자 ID")
    amount: float = Field(default=0.0, ge=0.0, description="환불 금액 (원)")
    reason: str = Field(default="", description="신고 사유 (분쟁 코드 등)")


@router.post("/feedback/chargeback", status_code=201)
def feedback_chargeback(req: ChargebackFeedbackRequest) -> dict[str, Any]:
    """W7.5-#4 — 사기 신고(chargeback) ground truth 라벨 기록."""
    entry = feedback_store.record(
        tx_id=req.tx_id,
        user_id=req.user_id,
        amount=req.amount,
        reason=req.reason,
    )
    return {
        "tx_id": entry.tx_id,
        "label": entry.label,
        "reported_at": entry.reported_at,
        "total_recorded": feedback_store.count(),
    }


@router.get("/feedback/chargeback")
def list_chargebacks(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    items = feedback_store.all()[-limit:]
    return {
        "count": len(items),
        "total": feedback_store.count(),
        "items": [
            {
                "tx_id": e.tx_id,
                "user_id": e.user_id,
                "amount": e.amount,
                "reason": e.reason,
                "label": e.label,
                "reported_at": e.reported_at,
            }
            for e in items
        ],
    }


@router.get("/feedback/metrics")
def feedback_metrics() -> dict[str, Any]:
    """평가 이력 + chargeback 라벨로 precision/recall/F1 계산."""
    # stats_collector 의 내부 deque 에 직접 접근 — slo_summary 와 동일 패턴
    with stats_collector._lock:  # type: ignore[attr-defined]
        entries = list(stats_collector._entries)  # type: ignore[attr-defined]
    return precision_recall_summary(entries)


@router.get("/risk-leakage-report")
def risk_leakage_report(total_processed_amount: float = Query(..., ge=0.0)) -> dict[str, Any]:
    try:
        report = generate_risk_leakage_report(total_processed_amount)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report
