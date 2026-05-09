"""W9-#10 — 감정 알림 누락 감사 로그 + 의존성 주입 테스트."""
from __future__ import annotations

import asyncio

from app.services.emotion_engine import (
    _audit_emotion_notify_failure,
    get_emotion_notify_audit,
    reset_emotion_notify_audit,
)


def test_audit_starts_empty():
    reset_emotion_notify_audit()
    s = get_emotion_notify_audit()
    assert s["total_failures"] == 0
    assert s["recent"] == []


def test_audit_records_failure():
    reset_emotion_notify_audit()
    _audit_emotion_notify_failure("u1", "RuntimeError('boom')")
    _audit_emotion_notify_failure("u2", "ConnectionError")
    s = get_emotion_notify_audit()
    assert s["total_failures"] == 2
    user_ids = {e["user_id"] for e in s["recent"]}
    assert user_ids == {"u1", "u2"}


def test_audit_respects_max():
    reset_emotion_notify_audit()
    for i in range(250):
        _audit_emotion_notify_failure(f"u{i}", "x")
    s = get_emotion_notify_audit()
    assert s["total_failures"] <= 200
    # recent 는 max 20 으로 슬라이스됐는지
    assert len(s["recent"]) == 20


def test_check_and_notify_di_signature():
    """notify_fn 인자 시그니처 — DI 가능하도록 keyword-only 로 노출."""
    from inspect import signature
    from app.services.emotion_engine import check_and_notify
    sig = signature(check_and_notify)
    assert "notify_fn" in sig.parameters
    assert sig.parameters["notify_fn"].kind.name == "KEYWORD_ONLY"
