"""W7-#2 — Latency 측정 미들웨어 + P99 응답 헤더.

매 요청에서 처리 시간을 측정하고 X-Process-Time-Ms 헤더로 응답.
경로별 누적 deque 에서 p50/p99 를 계산해 X-P50-Ms / X-P99-Ms 헤더 첨부.

별도 prometheus exporter 가 없을 때도 운영자가 curl 로 즉시 관측 가능.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_PER_PATH_MAX = 1000  # 경로당 최근 N건
_lock = threading.Lock()
_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_PER_PATH_MAX))


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def get_path_latency_summary() -> dict:
    """헬스체크용 — 경로별 p50/p99/avg/count."""
    out: dict[str, dict] = {}
    with _lock:
        for path, q in _history.items():
            vals = list(q)
            if not vals:
                continue
            out[path] = {
                "count": len(vals),
                "avg_ms": round(sum(vals) / len(vals), 3),
                "p50_ms": round(_percentile(vals, 50), 3),
                "p99_ms": round(_percentile(vals, 99), 3),
            }
    return out


def reset_latency_history() -> None:
    with _lock:
        _history.clear()


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        path_key = request.scope.get("route").path if request.scope.get("route") else request.url.path
        with _lock:
            _history[path_key].append(elapsed_ms)
            vals = list(_history[path_key])

        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.3f}"
        if len(vals) >= 5:
            response.headers["X-P50-Ms"] = f"{_percentile(vals, 50):.3f}"
            response.headers["X-P99-Ms"] = f"{_percentile(vals, 99):.3f}"
        return response
