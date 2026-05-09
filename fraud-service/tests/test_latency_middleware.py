"""W7-#2 — Latency 측정 미들웨어 + P99 응답 헤더 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.latency import (
    get_path_latency_summary,
    reset_latency_history,
)

client = TestClient(app)


def test_process_time_header_present():
    reset_latency_history()
    r = client.get("/health")
    assert r.status_code == 200
    assert "x-process-time-ms" in {k.lower() for k in r.headers.keys()}
    val = float(r.headers["X-Process-Time-Ms"])
    assert val >= 0


def test_p50_p99_after_warmup():
    reset_latency_history()
    for _ in range(6):
        client.get("/health")
    r = client.get("/health")
    headers = {k.lower(): v for k, v in r.headers.items()}
    assert "x-p50-ms" in headers
    assert "x-p99-ms" in headers
    p50 = float(headers["x-p50-ms"])
    p99 = float(headers["x-p99-ms"])
    assert p99 >= p50


def test_summary_endpoint():
    reset_latency_history()
    for _ in range(3):
        client.get("/health")
    summary = get_path_latency_summary()
    assert any("/health" in path for path in summary)


def test_admin_latency_endpoint():
    reset_latency_history()
    for _ in range(3):
        client.get("/health")
    r = client.get("/admin/api/latency")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
