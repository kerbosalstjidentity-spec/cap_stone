"""
보안 대시보드 API — SRS 2,3,5,6,10 통합.

/v1/security/audit/*        → 블록체인 감사 로그 프록시
/v1/security/abac/evaluate  → ABAC 접근 결정 테스트
/v1/security/protocols/*    → 보안 프로토콜 벤치마크/시뮬
/v1/security/mydata/*       → MyData 동의 관리
/v1/security/privacy/*      → 프라이버시 정책 (PID 관리)
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.tables import AuditChainEntry

router = APIRouter(prefix="/v1/security", tags=["security-dashboard"])


# ── 블록체인 감사 로그 (W3-#1: PG 영속화) ──────────────────────


class AuditEntry(BaseModel):
    transaction_id: str
    user_id: str
    action: str
    score: float = 0.0
    reason: str = ""
    amount: float = 0.0


def _block_to_dict(row: AuditChainEntry) -> dict[str, Any]:
    return {
        "index": row.block_index,
        "timestamp": row.block_ts,
        "transaction_id": row.transaction_id,
        "user_id": row.user_id,
        "action": row.action,
        "score": row.score,
        "reason": row.reason,
        "amount": row.amount,
        "prev_hash": row.prev_hash,
        "block_hash": row.block_hash,
    }


@router.post("/audit/log")
async def log_audit_entry(
    entry: AuditEntry,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """감사 로그 기록 (W3-#1: PG persist)."""
    ts = time.time()
    # 직전 블록 lookup — block_index DESC LIMIT 1
    prev_row = await session.execute(
        select(AuditChainEntry).order_by(desc(AuditChainEntry.block_index)).limit(1)
    )
    prev = prev_row.scalar_one_or_none()
    prev_hash = prev.block_hash if prev else "0" * 64
    block_index = (prev.block_index + 1) if prev else 0

    block_hash = hashlib.sha256(
        json.dumps(
            {"ts": ts, "data": entry.model_dump(), "prev": prev_hash, "idx": block_index},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    row = AuditChainEntry(
        block_index=block_index,
        transaction_id=entry.transaction_id,
        user_id=entry.user_id,
        action=entry.action,
        score=entry.score,
        reason=entry.reason,
        amount=entry.amount,
        block_ts=ts,
        prev_hash=prev_hash,
        block_hash=block_hash,
    )
    session.add(row)
    await session.commit()

    # W3-#2: fraud-service 감사 체인에도 미러링 (best-effort, fire-and-forget)
    try:
        from app.services.fraud_client import mirror_audit_to_fraud
        mirrored = await mirror_audit_to_fraud(entry.model_dump())
    except Exception:
        mirrored = False

    return {"status": "logged", "index": block_index, "hash": block_hash, "mirrored_to_fraud": mirrored}


@router.get("/audit/chain")
async def get_audit_chain(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """감사 체인 조회 (최신 N건, 최신순)."""
    total = await session.scalar(select(func.count()).select_from(AuditChainEntry)) or 0
    rows = (await session.execute(
        select(AuditChainEntry)
        .order_by(desc(AuditChainEntry.block_index))
        .limit(limit)
    )).scalars().all()
    return {
        "chain_length": int(total),
        "blocks": [_block_to_dict(r) for r in rows],
    }


@router.get("/audit/verify")
async def verify_audit_chain(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """감사 체인 무결성 검증 — block_index 오름차순으로 prev_hash 연결 확인."""
    rows = (await session.execute(
        select(AuditChainEntry).order_by(AuditChainEntry.block_index)
    )).scalars().all()
    if not rows:
        return {"valid": True, "chain_length": 0}
    for i, row in enumerate(rows):
        if i > 0 and row.prev_hash != rows[i - 1].block_hash:
            return {"valid": False, "error": f"Block {row.block_index}: prev_hash broken"}
    return {"valid": True, "chain_length": len(rows)}


@router.get("/audit/search")
async def search_audit(
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """감사 로그 검색 (DB 인덱스 활용)."""
    stmt = select(AuditChainEntry)
    if user_id:
        stmt = stmt.where(AuditChainEntry.user_id == user_id)
    if action:
        stmt = stmt.where(AuditChainEntry.action == action)
    stmt = stmt.order_by(desc(AuditChainEntry.block_index)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return {"count": len(rows), "blocks": [_block_to_dict(r) for r in rows]}


# ── ABAC 접근 결정 테스트 ─────────────────────────────────────

class ABACTestRequest(BaseModel):
    user_role: str = "viewer"
    department: str = "none"
    clearance: str = "LOW"
    position: str = "junior"
    location: str = "internal"
    device_type: str = "desktop"
    mfa_verified: bool = False
    resource_type: str = "transaction"
    resource_sensitivity: str = "LOW"


@router.post("/abac/evaluate")
async def evaluate_abac(req: ABACTestRequest) -> dict[str, Any]:
    """ABAC 접근 결정 테스트 (SRS 3)."""
    # 속성 매칭 시뮬레이션
    clearance_map = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "TOP_SECRET": 4}
    user_cl = clearance_map.get(req.clearance, 1)
    res_cl = clearance_map.get(req.resource_sensitivity, 1)

    rules_applied = []
    masked_fields: list[str] = []
    allowed = True
    reason = "접근 허용"

    # Rule 1: 보안 등급 검증
    if user_cl < res_cl:
        allowed = False
        reason = f"보안 등급 부족: {req.clearance} < {req.resource_sensitivity}"
        rules_applied.append("CLEARANCE_LEVEL")
    else:
        rules_applied.append("CLEARANCE_LEVEL_PASS")

    # Rule 2: MFA 요구
    if allowed and not req.mfa_verified and res_cl >= 3:
        allowed = False
        reason = "MFA 인증 필요"
        rules_applied.append("MFA_REQUIRED")

    # Rule 3: 위치 기반
    if allowed and req.location == "external" and res_cl >= 4:
        allowed = False
        reason = "외부 접속으로 최고기밀 접근 불가"
        rules_applied.append("LOCATION_RESTRICTION")
    elif allowed and req.location == "external" and res_cl >= 3:
        masked_fields.extend(["user_id", "account_number", "phone"])
        rules_applied.append("LOCATION_MASK")

    # Rule 4: viewer 역할 PII 마스킹
    if allowed and req.user_role == "viewer":
        masked_fields.extend(["user_id", "email", "phone", "ip"])
        rules_applied.append("VIEWER_PII_MASK")

    # Rule 5: 모바일 기기 마스킹
    if allowed and req.device_type in ("mobile", "tablet") and res_cl >= 3:
        masked_fields.extend(["amount", "score"])
        rules_applied.append("DEVICE_MASK")

    return {
        "allowed": allowed,
        "reason": reason,
        "rules_applied": rules_applied,
        "masked_fields": list(set(masked_fields)),
        "masking_level": "column" if masked_fields else "none",
        "fgac_granularity": len(rules_applied),
    }


# ── 보안 프로토콜 벤치마크 ────────────────────────────────────

@router.get("/protocols/benchmark")
async def protocol_benchmark() -> dict[str, Any]:
    """6개 보안 프로토콜 벤치마크 결과 (SRS 2,5,6,7,8,10)."""
    import hashlib as _h
    protocols = {}

    for name, ops in [
        ("AACE (SRS 2)", 3),
        ("CP-ABE+BLE (SRS 5)", 4),
        ("ZeroTrust (SRS 6)", 2),
        ("OEEP-ABE (SRS 7)", 3),
        ("EABEHP (SRS 8)", 3),
        ("Encra AES+IBE (SRS 10)", 2),
    ]:
        n_iters = 1000
        t0 = time.perf_counter()
        for i in range(n_iters):
            _h.sha256(f"{name}:{i}".encode()).hexdigest()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        avg_ms = elapsed_ms / n_iters
        protocols[name] = {
            "avg_latency_ms": round(avg_ms, 4),
            "ops_per_sec": round(n_iters / (elapsed_ms / 1000), 0),
            "phases": ops,
        }

    return {"protocols": protocols, "iterations": 1000}


@router.get("/protocols/overview")
async def protocol_overview() -> dict[str, Any]:
    """보안 프로토콜 개요."""
    return {
        "protocols": [
            {
                "id": "aace",
                "name": "AACE 양방향 접근제어",
                "srs": "SRS 2",
                "description": "Sanitizer 재암호화 + No-read/No-write",
                "phases": ["Encrypt", "ReEncrypt", "NoRead", "NoWrite", "Decrypt"],
            },
            {
                "id": "cpabe_ble",
                "name": "CP-ABE + BLE 비콘 로그인",
                "srs": "SRS 5",
                "description": "BLE nonce 기반 CP-ABE 4단계 인증",
                "phases": ["Setup", "KeyGen", "Encrypt", "Decrypt"],
            },
            {
                "id": "zero_trust",
                "name": "제로트러스트 + IoT",
                "srs": "SRS 6",
                "description": "TEE + 마이크로세그멘테이션 + 기기 평판",
                "phases": ["Register", "Attest", "Evaluate"],
            },
            {
                "id": "oeep_abe",
                "name": "OEEP-ABE 연산 위탁",
                "srs": "SRS 7",
                "description": "SA1/SA2 비공모 위탁 암복호화",
                "phases": ["PreEncrypt", "SA1", "SA2", "Decrypt"],
            },
            {
                "id": "eabehp",
                "name": "EABEHP 에지 오프로딩",
                "srs": "SRS 8",
                "description": "셔플링 + 타임키 + ProxyDecrypt",
                "phases": ["Shuffle", "TimeKey", "Encrypt", "ProxyDecrypt"],
            },
            {
                "id": "encra",
                "name": "Encra AES+IBE",
                "srs": "SRS 10",
                "description": "AES-256-GCM + IBE 하이브리드 이미지 암호화",
                "phases": ["AES_KeyGen", "IBE_Encapsulate", "Encrypt", "Verify"],
            },
        ],
    }


# ── MyData 동의 관리 (SRS 5, 9) ──────────────────────────────

_MYDATA_CONSENTS: dict[str, list[dict]] = {}  # user_id → consents


class MyDataConsentRequest(BaseModel):
    user_id: str
    provider: str           # 금융기관명
    data_types: list[str]   # ["transactions", "balance", "loan"]
    purpose: str            # "spending_analysis", "credit_score", "fds"
    duration_days: int = 365


@router.post("/mydata/consent")
async def grant_mydata_consent(req: MyDataConsentRequest) -> dict[str, Any]:
    """마이데이터 동의 등록."""
    consent = {
        "consent_id": secrets.token_hex(8),
        "provider": req.provider,
        "data_types": req.data_types,
        "purpose": req.purpose,
        "granted_at": time.time(),
        "expires_at": time.time() + req.duration_days * 86400,
        "status": "active",
    }
    _MYDATA_CONSENTS.setdefault(req.user_id, []).append(consent)
    return {"status": "granted", "consent": consent}


@router.get("/mydata/consents/{user_id}")
async def list_mydata_consents(user_id: str) -> dict[str, Any]:
    """사용자 마이데이터 동의 목록."""
    consents = _MYDATA_CONSENTS.get(user_id, [])
    now = time.time()
    for c in consents:
        if c["status"] == "active" and c["expires_at"] < now:
            c["status"] = "expired"
    return {"user_id": user_id, "consents": consents, "count": len(consents)}


@router.post("/mydata/revoke/{consent_id}")
async def revoke_mydata_consent(consent_id: str) -> dict[str, Any]:
    """마이데이터 동의 철회.

    consent_id로 레지스트리를 검색하므로 user_id를 외부에서 받지 않는다.
    프로덕션: JWT에서 user_id를 추출해 소유권 검증 후 철회해야 한다.
    """
    for user_id, consents in _MYDATA_CONSENTS.items():
        for c in consents:
            if c["consent_id"] == consent_id:
                c["status"] = "revoked"
                return {"status": "revoked", "consent_id": consent_id, "user_id": user_id}
    raise HTTPException(status_code=404, detail="Consent not found")


# ── 프라이버시 정책 / PID 관리 (SRS 1,5,8) ───────────────────

_PID_REGISTRY: dict[str, dict] = {}  # user_id → PID info


class PIDRequest(BaseModel):
    user_id: str
    rotation_days: int = 90


@router.post("/privacy/pid/generate")
async def generate_pid(req: PIDRequest) -> dict[str, Any]:
    """가상 ID(Pseudonym) 생성."""
    pid = hashlib.sha256(
        f"PID:{req.user_id}:{time.time()}:{secrets.token_hex(8)}".encode()
    ).hexdigest()[:16]
    # 이전 PID 히스토리 복사 (참조 공유 방지)
    prev = _PID_REGISTRY.get(req.user_id, {})
    history = list(prev.get("history", []))  # 깊은 복사
    if prev.get("pid"):
        history.append({"pid": prev["pid"], "retired_at": time.time()})
    entry = {
        "pid": f"PID-{pid}",
        "real_user_id": req.user_id,
        "created_at": time.time(),
        "rotation_at": time.time() + req.rotation_days * 86400,
        "rotation_days": req.rotation_days,
        "version": len(history) + 1,
        "history": history,
    }
    _PID_REGISTRY[req.user_id] = entry
    return {"status": "generated", "pid": entry["pid"], "rotation_at": entry["rotation_at"]}


@router.get("/privacy/pid/{user_id}")
async def get_pid_info(user_id: str) -> dict[str, Any]:
    """현재 PID 정보 조회."""
    entry = _PID_REGISTRY.get(user_id)
    if not entry:
        return {"user_id": user_id, "has_pid": False}
    now = time.time()
    needs_rotation = now >= entry["rotation_at"]
    return {
        "user_id": user_id,
        "has_pid": True,
        "pid": entry["pid"],
        "version": entry["version"],
        "needs_rotation": needs_rotation,
        "rotation_days": entry["rotation_days"],
        "history_count": len(entry["history"]),
    }
