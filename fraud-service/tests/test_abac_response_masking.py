"""W11-#1 — ABAC 결정이 응답에 실제 적용되는지 검증.

배경:
    그동안 미들웨어가 ``request.state.abac_decision`` 에 마스킹 결정을
    저장만 하고 라우터가 그것을 읽지 않아 8규칙의 MASK 액션이 무력화돼
    있었다. W11-#1 에서 미들웨어가 응답 본문을 가로채 마스킹을 적용하도록
    수정했고, 본 테스트는 그 결과를 검증한다.

검증 시나리오:
    1. ABE 비활성 (기본) — 미들웨어는 통과만, 응답 변형 없음
    2. auditor + external 위치 → LocationRestriction → MASK_COLUMN(user_id 등)
    3. analyst + internal + mfa + clearance:high → masking_level == none
"""
from __future__ import annotations

import json
from base64 import b64encode

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware import abe_auth as abe_mw
from app.services.blockchain_audit import audit_chain


def _token(attrs: dict) -> str:
    """ABE AttributeToken 페이로드를 base64 JSON 으로 인코딩."""
    return b64encode(
        json.dumps({"user_id": attrs.get("_uid", "u-test"), "attributes": attrs}).encode("utf-8")
    ).decode("ascii")


@pytest.fixture
def client_abe_on(monkeypatch):
    """ABE 미들웨어 활성화 + 정책 캐시 초기화."""
    monkeypatch.setattr(abe_mw, "_ABE_ENABLED", True)
    monkeypatch.setattr(abe_mw, "_policies", [])  # lazy 재로딩 강제
    return TestClient(app)


@pytest.fixture
def seed_audit_block():
    """user_id 가 명확히 식별되는 감사 블록 1개 적재."""
    audit_chain.append(
        transaction_id="tx-mask-001",
        user_id="alice-123",
        action="PASS",
        score=0.42,
        rule_ids=[],
        reason_code="",
        amount=12345.0,
    )
    yield


def test_external_auditor_user_id_is_masked(client_abe_on, seed_audit_block):
    """external 위치 auditor → LocationRestriction MASK_COLUMN — user_id 마스킹."""
    token = _token({
        "_uid": "auditor-1",
        "role": "auditor",
        "dept": "compliance",
        "clearance": "high",
        "location": "external",
        "device_type": "desktop",
        "mfa_verified": "true",
    })
    resp = client_abe_on.get("/v1/audit/recent?n=5", headers={"X-ABE-Token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 1
    # 적재된 user_id 가 마스킹되어 원본 그대로 노출되면 안 됨
    user_ids = [b.get("user_id") for b in body["blocks"]]
    assert "alice-123" not in user_ids, f"user_id 원본 노출됨: {user_ids}"
    masked_sample = next(u for u in user_ids if u and u != "SYSTEM")
    # _mask_value 규칙: 첫/끝 글자 + 가운데 별표
    assert "*" in masked_sample


def test_internal_admin_no_masking(client_abe_on, seed_audit_block):
    """내부 + MFA + high clearance admin → 마스킹 없음.

    (admin 사용 이유: BusinessHoursRule 이 업무시간 외에도 마스킹을 적용하지만
    role=admin 은 예외. 시간대 의존성을 제거한 안정 케이스.)
    """
    token = _token({
        "_uid": "admin-1",
        "role": "admin",
        "dept": "fraud_team",
        "clearance": "high",
        "location": "internal",
        "device_type": "desktop",
        "mfa_verified": "true",
    })
    resp = client_abe_on.get("/v1/audit/recent?n=5", headers={"X-ABE-Token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 정상 응답 — 원본 user_id 노출 확인
    user_ids = [b.get("user_id") for b in body["blocks"]]
    assert "alice-123" in user_ids


def test_mobile_high_sensitivity_masks_cells(client_abe_on, seed_audit_block):
    """mobile 기기 + HIGH 리소스 → DeviceTypeRule MASK_CELL [amount, score]."""
    token = _token({
        "_uid": "auditor-2",
        "role": "auditor",
        "dept": "compliance",
        "clearance": "high",
        "location": "internal",
        "device_type": "mobile",
        "mfa_verified": "true",
    })
    resp = client_abe_on.get("/v1/audit/recent?n=5", headers={"X-ABE-Token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 적재된 amount(12345.0) 와 score(0.42) 가 그대로 노출되면 안 됨
    block = next(b for b in body["blocks"] if b.get("transaction_id") == "tx-mask-001")
    assert block.get("amount") != 12345.0, "amount 마스킹 누락"
    assert block.get("score") != 0.42, "score 마스킹 누락"


def test_abe_disabled_passthrough(seed_audit_block):
    """ABE 비활성 시 응답 그대로 통과 (회귀 방지)."""
    # 별도 client — 기본값 (_ABE_ENABLED=False) 사용
    client = TestClient(app)
    resp = client.get("/v1/audit/recent?n=5")
    assert resp.status_code == 200
    body = resp.json()
    user_ids = [b.get("user_id") for b in body["blocks"]]
    assert "alice-123" in user_ids  # 마스킹 없음


# ── W11-#2: ABE encrypted_fields (revocation-aware) ─────────────


def test_revocation_mid_flight_masks_encrypted_fields(client_abe_on, seed_audit_block, monkeypatch):
    """진입 시 정책 매칭은 통과했으나 응답 시점에 속성이 취소된 경우
    encrypted_fields 만 ENCRYPTED 마커로 마스킹된다 (TOCTOU 방어)."""
    from app.services import abe_engine as abe_mod

    # 진입 시점 revocation 필터를 비활성화해 정책 통과를 보장
    monkeypatch.setattr(abe_mw, "_filter_revoked_attrs", lambda uid, attrs: attrs)
    # 응답 시점에 role:auditor 가 취소되도록 미리 등록
    abe_mod.revocation_manager.revoke("auditor-revoked", "role:auditor")

    try:
        token = _token({
            "_uid": "auditor-revoked",
            "role": "auditor",
            "dept": "compliance",
            "clearance": "high",
            "location": "internal",
            "device_type": "desktop",
            "mfa_verified": "true",
        })
        resp = client_abe_on.get("/v1/audit/recent?n=5", headers={"X-ABE-Token": token})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # encrypted_fields = ["user_id", "amount", "score"] (yaml GET /v1/audit/*)
        target = next(b for b in body["blocks"] if b.get("transaction_id") == "tx-mask-001")
        assert target["user_id"] == "[ENCRYPTED: 접근 권한 부족]"
        assert target["amount"] == "[ENCRYPTED: 접근 권한 부족]"
        assert target["score"] == "[ENCRYPTED: 접근 권한 부족]"
    finally:
        # 글로벌 revocation_manager 청소
        abe_mod.revocation_manager._revoked.pop("auditor-revoked:role:auditor", None)


def test_valid_user_sees_unmasked_encrypted_fields(client_abe_on, seed_audit_block):
    """정상 사용자 — encrypted_fields 가 정의돼 있어도 정책을 만족하므로 원본 노출.

    (admin 사용 이유: BusinessHoursRule 의 시간대 의존성을 회피.)
    """
    token = _token({
        "_uid": "admin-clean",
        "role": "admin",
        "dept": "fraud_team",
        "clearance": "high",
        "location": "internal",
        "device_type": "desktop",
        "mfa_verified": "true",
    })
    resp = client_abe_on.get("/v1/audit/recent?n=5", headers={"X-ABE-Token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    target = next(b for b in body["blocks"] if b.get("transaction_id") == "tx-mask-001")
    assert target["user_id"] == "alice-123"
    assert target["amount"] == 12345.0
