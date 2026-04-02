"""
API Key 인증 미들웨어.

헤더: X-Fraud-Service-Key
환경변수:
  API_KEY_ENABLED   true/false (기본 false — 개발 편의)
  API_KEY           유효한 키 (쉼표로 여러 개 가능)
  API_KEY_EXEMPT    인증 제외 경로 prefix (기본: /health,/docs,/redoc,/openapi.json,/admin)

Spring Boot 내부망 호출 시 헤더에 키 포함.
"""
from __future__ import annotations

import os

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_ENABLED = os.getenv("API_KEY_ENABLED", "false").lower() == "true"
_VALID_KEYS: set[str] = {
    k.strip() for k in os.getenv("API_KEY", "").split(",") if k.strip()
}
_HEADER = "X-Fraud-Service-Key"

_EXEMPT_PREFIXES = tuple(
    p.strip()
    for p in os.getenv(
        "API_KEY_EXEMPT",
        "/health,/docs,/redoc,/openapi.json,/admin,/",
    ).split(",")
    if p.strip()
)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _ENABLED:
            return await call_next(request)

        path = request.url.path

        # 루트 정확 일치 or 제외 prefix 시작이면 통과
        if path == "/" or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        key = request.headers.get(_HEADER, "")
        if not key or key not in _VALID_KEYS:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": f"유효한 '{_HEADER}' 헤더가 필요합니다.",
                },
            )

        return await call_next(request)
