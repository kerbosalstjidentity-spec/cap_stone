"""W8-#4 — 감사 로그 5년 보존 정책 헬퍼 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.audit_retention import (
    classify_age,
    count_expired_sync,
    cutoff_datetime,
    retention_days,
)


def test_default_retention_5years():
    assert retention_days() >= 1825  # 5년 = 1825일


def test_env_override(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    assert retention_days() == 30


def test_cutoff_in_past():
    now = datetime.now(tz=timezone.utc)
    assert cutoff_datetime() < now


def test_classify_active():
    ts = datetime.now(tz=timezone.utc) - timedelta(days=100)
    assert classify_age(ts) == "active"


def test_classify_warning(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "100")
    now = datetime.now(tz=timezone.utc)
    # 만료 20일 전 → 80일 경과
    ts = now - timedelta(days=80)
    assert classify_age(ts, now=now) == "warning"


def test_classify_expired(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    now = datetime.now(tz=timezone.utc)
    ts = now - timedelta(days=60)
    assert classify_age(ts, now=now) == "expired"


def test_count_expired_dict(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    now = datetime.now(tz=timezone.utc)
    items = [
        {"created_at": now - timedelta(days=10)},
        {"created_at": now - timedelta(days=40)},
        {"created_at": (now - timedelta(days=100)).isoformat()},  # ISO 문자열
        {"created_at": None},
    ]
    assert count_expired_sync(items) == 2


def test_count_expired_orm_like(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")

    class _R:
        def __init__(self, ts):
            self.created_at = ts

    now = datetime.now(tz=timezone.utc)
    items = [_R(now - timedelta(days=40)), _R(now - timedelta(days=10))]
    assert count_expired_sync(items) == 1
