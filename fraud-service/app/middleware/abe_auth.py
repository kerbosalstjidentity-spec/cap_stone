"""
Layer 2 — CP-ABE 속성 기반 접근 제어 미들웨어.

기존 API Key 미들웨어와 **공존** (API Key → 기본 인증, ABE → 세분화 접근 제어).

헤더:
  X-ABE-Token: Base64 인코딩된 JSON {"user_id": "...", "attributes": {"role": "analyst", ...}}

동작:
  1. 토큰이 없으면 → 기본 viewer 권한 부여
  2. 토큰이 있으면 → 속성 추출 → 정책 매칭 → 접근 허용/거부
  3. 접근 거부 시 → 403 Forbidden
  4. 접근 허용 시 → request.state에 속성 정보 저장 (후속 필드 필터링용)
"""
from __future__ import annotations

import json
import os
from base64 import b64decode
from pathlib import Path

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.services.abe_engine import (
    AccessPolicy,
    AttributeToken,
    evaluate_access_structure,
    find_policy,
    load_policies,
)

_ABE_ENABLED = os.getenv("ABE_ENABLED", "false").lower() == "true"
_TOKEN_HEADER = "X-ABE-Token"

# 정책 로드 (환경변수 또는 기본 경로)
_POLICY_PATH = os.getenv(
    "ABE_POLICY_PATH",
    str(Path(__file__).resolve().parents[2] / "policies" / "abe_access_policy_v1.yaml"),
)

_policies: list[AccessPolicy] = []

_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/")

# 기본 속성 (토큰 미제공 시)
_DEFAULT_ATTRS = {"role": "viewer", "dept": "none", "clearance": "low"}


def _load_policies_lazy() -> list[AccessPolicy]:
    global _policies
    if not _policies and Path(_POLICY_PATH).exists():
        _policies = load_policies(_POLICY_PATH)
    return _policies


class AbeAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _ABE_ENABLED:
            # ABE 비활성 시 기본 속성 부여 후 통과
            request.state.abe_attrs = _DEFAULT_ATTRS
            request.state.abe_token = None
            return await call_next(request)

        path = request.url.path
        method = request.method

        # 제외 경로
        if path == "/" or any(path.startswith(p) for p in _EXEMPT_PREFIXES if p != "/"):
            request.state.abe_attrs = _DEFAULT_ATTRS
            request.state.abe_token = None
            return await call_next(request)

        # 토큰 파싱
        raw = request.headers.get(_TOKEN_HEADER, "")
        if raw:
            try:
                decoded = json.loads(b64decode(raw).decode("utf-8"))
                token = AttributeToken(
                    user_id=decoded.get("user_id", "unknown"),
                    attributes=decoded.get("attributes", {}),
                )
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Bad Request", "detail": "유효하지 않은 ABE 토큰입니다."},
                )
        else:
            token = AttributeToken(user_id="anonymous", attributes=_DEFAULT_ATTRS)

        # 정책 매칭
        policies = _load_policies_lazy()
        policy = find_policy(policies, method, path)

        if policy:
            user_attr_set = token.attr_set()
            if not evaluate_access_structure(policy.access_structure, user_attr_set):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "Forbidden",
                        "detail": "속성 기반 접근 제어: 요청된 리소스에 대한 접근 권한이 없습니다.",
                        "required_policy": policy.access_structure,
                        "your_attributes": sorted(user_attr_set),
                    },
                )

        # 속성 정보를 request.state에 저장 (응답 필터링용)
        request.state.abe_attrs = token.attributes
        request.state.abe_token = token
        return await call_next(request)
