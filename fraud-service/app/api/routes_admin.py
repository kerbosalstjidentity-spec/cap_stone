"""
관리형 대시보드 HTML + 상태/지표 JSON.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, settings
from app.scoring.model_loader import load_model_bundle, resolve_model_path
from app.services.fraud_service import SYSTEM_CONFIG
from app.services.rule_engine import rule_engine
from app.services.stats_collector import stats_collector
from app.services.access_list import access_list
from app.services import audit_logger
from app.scoring import ab_test

router = APIRouter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))


def _outputs_dir() -> Path | None:
    raw = settings.capstone_outputs_dir or os.environ.get("CAPSTONE_OUTPUTS_DIR")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p if p.is_dir() else None


def _read_json(name: str) -> dict | None:
    d = _outputs_dir()
    if d is None:
        return None
    f = d / name
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/api/status")
def admin_status():
    path = resolve_model_path()
    bundle = load_model_bundle()
    return {
        "service": "fraud-service",
        "model": {
            "configured_path": str(path) if path else None,
            "loaded": bundle is not None,
        },
        "metrics": {
            "holdout": _read_json("metrics_open_val_holdout.json"),
            "monitor_test": _read_json("monitor_open_test_full.json"),
        },
        "outputs_dir": str(_outputs_dir()) if _outputs_dir() else None,
    }


@router.get("/api/rules")
def admin_rules():
    return {"rules": rule_engine.list_rules()}


@router.post("/api/rules/{rule_id}/toggle")
def admin_toggle_rule(rule_id: str):
    new_state = rule_engine.toggle_rule(rule_id)
    if new_state is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"규칙 없음: {rule_id}")
    return {"rule_id": rule_id, "enabled": new_state}


@router.patch("/api/threshold")
def admin_set_threshold(body: dict):
    """
    body 예시: {"BLOCK_THRESHOLD": 0.9, "REVIEW_THRESHOLD": 0.4}
    SYSTEM_CONFIG에 있는 키만 수정 허용.
    """
    updated = {}
    allowed = {"BLOCK_THRESHOLD", "REVIEW_THRESHOLD", "P99_THRESHOLD",
                "AMOUNT_BLOCK_THRESHOLD", "AMOUNT_REVIEW_THRESHOLD"}
    for k, v in body.items():
        if k in allowed:
            SYSTEM_CONFIG[k] = float(v)
            updated[k] = float(v)
    return {"updated": updated, "current": {k: SYSTEM_CONFIG[k] for k in allowed}}


@router.get("/api/stats")
def admin_stats():
    return stats_collector.summary()


# --- W5-#1: 앙상블 가중치 동적 조정 ---

@router.get("/api/ensemble-weights")
def admin_get_ensemble_weights():
    from app.scoring.ensemble import get_weights
    return get_weights()


@router.patch("/api/ensemble-weights")
def admin_set_ensemble_weights(body: dict):
    """body 예시: {"alpha": 0.6, "beta": 0.4}. 합 0~1.5 안전 클립."""
    from app.scoring.ensemble import set_weights
    return set_weights(alpha=body.get("alpha"), beta=body.get("beta"))


# --- W7.5-#6: SLO 대시보드 ---

@router.get("/api/latency")
def admin_latency():
    """경로별 p50/p99/avg latency — W7-#2."""
    from app.middleware.latency import get_path_latency_summary
    return get_path_latency_summary()


@router.get("/api/slo")
def admin_slo(bucket_minutes: int = 1, buckets: int = 60):
    """시나리오별 검출률·latency p50/p99·FN/FP 비율·시계열."""
    return stats_collector.slo_summary(
        bucket_minutes=max(1, bucket_minutes),
        buckets=max(1, min(buckets, 240)),
    )


@router.get("/api/alarm")
def admin_alarm_status():
    """W7-#4: 자동 롤백 상태 + 마지막 체크 신호."""
    from app.services.alarm_manager import alarm_manager
    return alarm_manager.state()


@router.post("/api/alarm/check")
def admin_alarm_check(body: dict | None = None):
    """W7-#4: 즉시 체크 (force=true 면 무조건 롤백 트리거)."""
    from app.services.alarm_manager import alarm_manager
    force = bool((body or {}).get("force", False))
    return alarm_manager.check_and_act(force=force)


@router.post("/api/alarm/restore")
def admin_alarm_restore():
    """W7-#4: 롤백 해제 + 가중치 복원."""
    from app.services.alarm_manager import alarm_manager
    return alarm_manager.restore_default_weights()


@router.get("/api/drift")
def admin_drift(threshold: float = 0.2):
    """W7-#1: 피처별 KS 통계량 + 분위수 차이 + 드리프트 여부."""
    from app.services.drift_detector import drift_detector
    return drift_detector.report(threshold=max(0.0, min(1.0, threshold)))


@router.get("/api/score-distribution")
def admin_score_distribution(days: int = 7):
    """W7-#3: 일별 점수 분포 (mean/p50/p95/p99/min/max/block_rate)."""
    return stats_collector.score_distribution_daily(days=max(1, min(days, 90)))


@router.delete("/api/stats")
def admin_reset_stats():
    stats_collector.reset()
    return {"reset": True}


# --- A/B 테스트 통계 ---

# W7-#5: A/B 트래픽 비율 동적 조정
@router.get("/api/ab-traffic")
def admin_ab_traffic():
    return {"traffic_pct": ab_test.get_traffic_pct()}


@router.patch("/api/ab-traffic")
def admin_set_ab_traffic(body: dict):
    """body 예시: {"traffic_pct": 10}. 0~100 클립."""
    pct = body.get("traffic_pct")
    if pct is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="traffic_pct 필수")
    new = ab_test.set_traffic_pct(pct)
    return {"traffic_pct": new}


@router.get("/api/ab-stats")
def admin_ab_stats():
    return {"ab_stats": ab_test.get_stats()}


@router.delete("/api/ab-stats")
def admin_reset_ab_stats():
    ab_test.reset_stats()
    return {"reset": True}


# --- Audit log ---

@router.get("/api/audit")
def admin_audit(n: int = 50):
    """최근 n건 audit 로그 반환 (기본 50)."""
    return {"logs": audit_logger.tail(n)}


# --- Blacklist / Whitelist ---

@router.get("/api/blacklist")
def get_blacklist():
    return {"blacklist": access_list.blacklist_all()}


@router.post("/api/blacklist", status_code=201)
def add_blacklist(body: dict):
    kind = body.get("kind", "user_id")
    value = body.get("value", "")
    reason = body.get("reason", "")
    if not value or kind not in ("user_id", "ip"):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="kind(user_id|ip)와 value 필수")
    access_list.blacklist_add(kind, value, reason)
    return {"kind": kind, "value": value, "reason": reason}


@router.delete("/api/blacklist")
def remove_blacklist(body: dict):
    kind = body.get("kind", "user_id")
    value = body.get("value", "")
    removed = access_list.blacklist_remove(kind, value)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="해당 항목 없음")
    return {"removed": True, "kind": kind, "value": value}


@router.get("/api/whitelist")
def get_whitelist():
    return {"whitelist": access_list.whitelist_all()}


@router.post("/api/whitelist", status_code=201)
def add_whitelist(body: dict):
    user_id = body.get("user_id", "")
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="user_id 필수")
    access_list.whitelist_add(user_id)
    return {"user_id": user_id}


@router.delete("/api/whitelist")
def remove_whitelist(body: dict):
    user_id = body.get("user_id", "")
    removed = access_list.whitelist_remove(user_id)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="해당 user_id 없음")
    return {"removed": True, "user_id": user_id}


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"title": "Fraud 서비스 관리"},
    )
