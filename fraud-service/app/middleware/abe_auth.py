"""
Layer 2 — CP-ABE 속성 기반 접근 제어 미들웨어.

W1-#5: ABAC 엔진 통합 wiring.
- 1단계 ABE 정책 매칭 (access_structure 평가, RBAC 수준)
- 2단계 ABACEngine 평가 — 8가지 규칙 (시간/위치/기기/MFA/위협레벨/기밀등급/부서/마스킹)
- 마스킹 결정은 request.state.abac_decision 에 저장 → 응답 직렬화 시 활용
- revocation_manager.filter_attrs() 적용 (W8-#8 선반영)

W1-#7: 운영 모드에서 정책/속성 노출 차단.
- ENV=production 이면 403 응답에서 `required_policy`/`your_attributes` 제거
- dev에서는 디버깅 편의 위해 그대로 유지
"""
from __future__ import annotations

import json
import os
from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.services.abac_engine import (
    ABACEngine,
    ClearanceLevel,
    EnvironmentAttributes,
    ResourceAttributes,
    SubjectAttributes,
    apply_abac_masking,
)
from app.services.abe_engine import (
    AccessPolicy,
    AttributeToken,
    evaluate_access_structure,
    filter_response,
    find_policy,
    load_policies,
)

_ABE_ENABLED = os.getenv("ABE_ENABLED", "false").lower() == "true"
_TOKEN_HEADER = "X-ABE-Token"
# W12-#1: 토큰 서명 검증 강제. production 에서는 자동 강제, dev/test 에서는 기본 off.
_REQUIRE_SIGNATURE = os.getenv("ABE_REQUIRE_SIGNATURE", "").lower() == "true" or (
    (os.getenv("ENV") or os.getenv("APP_ENV") or "").lower() in ("production", "prod")
)

# 정책 로드 (환경변수 또는 기본 경로)
_POLICY_PATH = os.getenv(
    "ABE_POLICY_PATH",
    str(Path(__file__).resolve().parents[2] / "policies" / "abe_access_policy_v1.yaml"),
)

_policies: list[AccessPolicy] = []
_abac_engine = ABACEngine()

_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/")

# 기본 속성 (토큰 미제공 시)
_DEFAULT_ATTRS = {"role": "viewer", "dept": "none", "clearance": "low"}


def _is_prod() -> bool:
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "development").lower()
    return env in ("production", "prod")


def _load_policies_lazy() -> list[AccessPolicy]:
    global _policies
    if not _policies and Path(_POLICY_PATH).exists():
        _policies = load_policies(_POLICY_PATH)
    return _policies


def _attrs_to_subject(user_id: str, attrs: dict) -> SubjectAttributes:
    """ABE AttributeToken → ABACEngine SubjectAttributes 변환.

    누락된 속성은 기본값으로 채운다 (DENY 가 아니라 LOW 권한으로 폴백).
    """
    clearance_map = {
        "low": ClearanceLevel.LOW,
        "medium": ClearanceLevel.MEDIUM,
        "high": ClearanceLevel.HIGH,
        "top_secret": ClearanceLevel.TOP_SECRET,
        "critical": ClearanceLevel.TOP_SECRET,
    }
    clearance_str = (attrs.get("clearance") or "low").lower()
    return SubjectAttributes(
        user_id=user_id,
        role=attrs.get("role", "viewer"),
        department=attrs.get("dept", "none"),
        clearance=clearance_map.get(clearance_str, ClearanceLevel.LOW),
        position=attrs.get("position", ""),
        location=attrs.get("location", "internal"),
        device_type=attrs.get("device_type", "desktop"),
        mfa_verified=str(attrs.get("mfa_verified", "false")).lower() == "true",
        ip_country=attrs.get("ip_country", "KR"),
    )


def _path_to_resource(path: str, sensitivity_hint: str | None = None) -> ResourceAttributes:
    """URL 경로에서 ResourceAttributes 추론.

    - /v1/audit/*  → audit_log, HIGH
    - /v1/fraud/*  → transaction, HIGH
    - /v1/profile/* → profile, MEDIUM
    - 그 외       → generic, LOW
    """
    if path.startswith("/v1/audit"):
        return ResourceAttributes(resource_type="audit_log", sensitivity=ClearanceLevel.HIGH, data_classification="confidential")
    if path.startswith("/v1/fraud") or path.startswith("/v1/score"):
        return ResourceAttributes(resource_type="transaction", sensitivity=ClearanceLevel.HIGH, data_classification="confidential")
    if path.startswith("/v1/profile") or path.startswith("/v1/users"):
        return ResourceAttributes(resource_type="profile", sensitivity=ClearanceLevel.MEDIUM, data_classification="internal")
    return ResourceAttributes(resource_type="generic", sensitivity=ClearanceLevel.LOW, data_classification="public")


def _filter_revoked_attrs(user_id: str, attrs: dict) -> dict:
    """W8-#8: revocation_manager.filter_attrs(user_id, attr_set) 미들웨어 적용.

    AttributeToken.attributes 는 {key: value} dict 형태.
    revocation_manager.filter_attrs() 는 ``"key:value"`` 또는 ``"value"`` 형태의
    문자열 set 을 받으므로 dict → set 직렬화 후 필터, 다시 dict 복원.
    """
    try:
        from app.services.abe_engine import revocation_manager
        if not hasattr(revocation_manager, "filter_attrs"):
            return attrs
        # dict → {"key:value"} set (revocation key 형식)
        attr_set: set[str] = set()
        kv_map: dict[str, str] = {}
        for k, v in (attrs or {}).items():
            token_str = f"{k}:{v}"
            attr_set.add(token_str)
            kv_map[token_str] = k
        filtered = revocation_manager.filter_attrs(user_id, attr_set)
        if filtered == attr_set:
            return attrs
        # 남은 키만 dict 로 복원
        kept_keys = {kv_map[t] for t in filtered if t in kv_map}
        return {k: v for k, v in attrs.items() if k in kept_keys}
    except Exception:
        return attrs


def _unauthorized_response(detail_dev: str) -> JSONResponse:
    """401 응답 — 토큰 서명/만료 검증 실패. production 에서는 상세 사유 숨김."""
    body = {
        "error": "Unauthorized",
        "detail": "유효하지 않은 인증 토큰입니다." if _is_prod() else detail_dev,
    }
    return JSONResponse(status_code=401, content=body)


def _is_token_expired(expires_at: str) -> bool:
    """expires_at ISO 8601 문자열이 현재 시각보다 과거면 True. 빈 값은 무시(만료 미설정)."""
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < datetime.now(tz=timezone.utc)
    except Exception:
        # 파싱 불가 → 보수적으로 만료 취급
        return True


def _forbidden_response(detail_dev: str, policy: str | None, user_attrs: list[str]) -> JSONResponse:
    """403 응답 — production에서는 정책/속성 마스킹 (W1-#7)."""
    body: dict = {
        "error": "Forbidden",
        "detail": "요청한 리소스에 대한 접근 권한이 없습니다." if _is_prod() else detail_dev,
    }
    if not _is_prod():
        if policy:
            body["required_policy"] = policy
        if user_attrs:
            body["your_attributes"] = user_attrs
    return JSONResponse(status_code=403, content=body)


class AbeAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _ABE_ENABLED:
            # ABE 비활성 시 기본 속성 부여 후 통과
            request.state.abe_attrs = _DEFAULT_ATTRS
            request.state.abe_token = None
            request.state.abac_decision = None
            return await call_next(request)

        path = request.url.path
        method = request.method

        # 제외 경로
        if path == "/" or any(path.startswith(p) for p in _EXEMPT_PREFIXES if p != "/"):
            request.state.abe_attrs = _DEFAULT_ATTRS
            request.state.abe_token = None
            request.state.abac_decision = None
            return await call_next(request)

        # ── 1) 토큰 파싱 ──────────────────────────
        raw = request.headers.get(_TOKEN_HEADER, "")
        if raw:
            try:
                decoded = json.loads(b64decode(raw).decode("utf-8"))
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Bad Request", "detail": "유효하지 않은 ABE 토큰입니다."},
                )
            _uid = decoded.get("user_id", "unknown")
            _issued = decoded.get("issued_at", "")
            _sig = decoded.get("signature", "")
            _expires = decoded.get("expires_at", "")
            raw_attrs = decoded.get("attributes", {}) or {}

            # W12-#1: 만료 검증 (expires_at 가 설정된 경우만)
            if _is_token_expired(_expires):
                return _unauthorized_response("토큰 만료")

            # W12-#1: HMAC 서명 검증.
            # production 또는 ABE_REQUIRE_SIGNATURE=true 면 강제, 서명 없거나 불일치 시 401.
            # dev/test 에서는 서명 미제공 토큰을 허용하되, 서명이 *제공된* 경우 검증은 항상 수행.
            from app.services.abe_engine import _ABE_SECRET
            if _sig or _REQUIRE_SIGNATURE:
                probe = AttributeToken(
                    user_id=_uid, attributes=raw_attrs,
                    issued_at=_issued, signature=_sig, expires_at=_expires,
                )
                if not probe.verify_signature(_ABE_SECRET):
                    return _unauthorized_response("토큰 서명 불일치")

            # 취소된 속성은 미들웨어 단계에서 즉시 제거 (W8-#8) — 서명 검증 후
            effective_attrs = _filter_revoked_attrs(_uid, raw_attrs)
            token = AttributeToken(
                user_id=_uid, attributes=effective_attrs,
                issued_at=_issued, signature=_sig, expires_at=_expires,
            )
        else:
            if _REQUIRE_SIGNATURE:
                return _unauthorized_response("토큰 누락 — production 에서는 X-ABE-Token 필수")
            token = AttributeToken(user_id="anonymous", attributes=_DEFAULT_ATTRS)

        # ── 2) ABE 정책 매칭 (RBAC 수준) ─────────
        policies = _load_policies_lazy()
        policy = find_policy(policies, method, path)
        user_attr_set = token.attr_set()

        if policy and not evaluate_access_structure(policy.access_structure, user_attr_set):
            return _forbidden_response(
                detail_dev="속성 기반 접근 제어: 정책 미충족",
                policy=policy.access_structure,
                user_attrs=sorted(user_attr_set),
            )

        # ── 3) ABACEngine 평가 (W1-#5 wiring) ────
        # 8가지 규칙 (시간/위치/기기/MFA/위협레벨/기밀등급/부서/마스킹)
        subject = _attrs_to_subject(token.user_id, token.attributes)
        resource = _path_to_resource(path)
        env = EnvironmentAttributes()  # 현재 시각 자동 설정
        decision = _abac_engine.evaluate(subject, resource, env)

        if not decision.allowed:
            return _forbidden_response(
                detail_dev=f"ABAC: {decision.reason} (rules={decision.applied_rules})",
                policy=None,
                user_attrs=sorted(user_attr_set),
            )

        # 통과 — 후속 핸들러가 마스킹 결정을 활용할 수 있도록 state에 저장
        request.state.abe_attrs = token.attributes
        request.state.abe_token = token
        request.state.abac_decision = decision

        response = await call_next(request)

        # W11-#1: ABAC 결정의 masked_fields 를 응답에 적용 (라우터 wiring 갭 메움)
        # 200 + application/json 응답만 가공. SSE/스트리밍/에러는 원본 유지.
        if (
            decision.masking_level != "none"
            and decision.masked_fields
            and 200 <= response.status_code < 300
            and response.headers.get("content-type", "").startswith("application/json")
        ):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                payload = json.loads(body)
            except Exception:
                # 파싱 실패 시 원본 그대로
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
                    media_type=response.media_type,
                )
            masked = apply_abac_masking(payload, decision)
            # W11-#2: ABE 정책의 encrypted_fields 적용 (revocation-aware TOCTOU 재검증).
            # 요청 진입 시 정책 매칭이 통과했어도, 처리 도중 속성이 취소되면
            # 응답 시점 effective_attrs 로 재평가하여 민감 필드만 마스킹.
            if policy and policy.encrypted_fields and isinstance(masked, dict):
                masked = filter_response(
                    masked,
                    encrypted_fields=policy.encrypted_fields,
                    user_attrs=user_attr_set,
                    access_structure=policy.access_structure,
                    user_id=token.user_id,
                )
            return JSONResponse(content=masked, status_code=response.status_code)

        # 마스킹 결정이 없어도 정책 encrypted_fields 가 있으면 revocation 재검증
        if (
            policy
            and policy.encrypted_fields
            and 200 <= response.status_code < 300
            and response.headers.get("content-type", "").startswith("application/json")
        ):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                payload = json.loads(body)
            except Exception:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
                    media_type=response.media_type,
                )
            if isinstance(payload, dict):
                payload = filter_response(
                    payload,
                    encrypted_fields=policy.encrypted_fields,
                    user_attrs=user_attr_set,
                    access_structure=policy.access_structure,
                    user_id=token.user_id,
                )
            return JSONResponse(content=payload, status_code=response.status_code)

        return response
