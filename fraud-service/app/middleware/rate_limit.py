"""
슬라이딩 윈도우 Rate Limiter 미들웨어.

외부 의존성 없이 순수 Python으로 구현.
IP별 요청 횟수를 슬라이딩 윈도우(기본 60초)로 추적.

환경변수:
  RATE_LIMIT_RPM      최대 요청 수 / 분 (기본 120)
  RATE_LIMIT_ENABLED  true/false (기본 true)
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
_RPM = int(os.getenv("RATE_LIMIT_RPM", "120"))
_WINDOW = 60.0  # seconds

_lock = threading.Lock()
# IP → deque of timestamps
_windows: dict[str, deque[float]] = defaultdict(deque)

# 제한 적용 경로 프리픽스 (Admin / health 제외)
_LIMITED_PREFIXES = ("/v1/",)
_EXEMPT_PATHS = {"/health", "/health/detail", "/docs", "/openapi.json", "/redoc"}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _ENABLED:
            return await call_next(request)

        path = request.url.path
        if path in _EXEMPT_PATHS or not any(path.startswith(p) for p in _LIMITED_PREFIXES):
            return await call_next(request)

        ip = _get_client_ip(request)
        now = time.monotonic()

        with _lock:
            dq = _windows[ip]
            # 윈도우 밖 타임스탬프 제거
            while dq and now - dq[0] > _WINDOW:
                dq.popleft()

            if len(dq) >= _RPM:
                oldest = dq[0]
                retry_after = int(_WINDOW - (now - oldest)) + 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "detail": f"분당 {_RPM}회 초과. {retry_after}초 후 재시도하세요.",
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)

        return await call_next(request)
