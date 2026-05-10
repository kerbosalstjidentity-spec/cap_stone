"""W8-#5 — 알림 채널 우선순위 + 중복 억제 테스트."""
from __future__ import annotations

import time

from app.services.alert_dedup import AlertDedup


def test_first_allow_then_deduplicate():
    d = AlertDedup(ttl_sec=60)
    assert d.allow("u1", "fraud", "BLOCK 1억원") is True
    assert d.allow("u1", "fraud", "BLOCK 1억원") is False  # 동일 → 억제
    assert d.allow("u1", "fraud", "BLOCK 다른건") is True   # 다른 메시지 → 허용
    assert d.allow("u2", "fraud", "BLOCK 1억원") is True   # 다른 사용자 → 허용


def test_different_kind_separate_dedup():
    d = AlertDedup(ttl_sec=60)
    assert d.allow("u1", "fraud", "msg") is True
    assert d.allow("u1", "stepup", "msg") is True  # 종류 달라서 별도


def test_ttl_expiry_allows_again():
    d = AlertDedup(ttl_sec=1)
    assert d.allow("u1", "k", "m") is True
    assert d.allow("u1", "k", "m") is False
    time.sleep(1.1)
    assert d.allow("u1", "k", "m") is True


def test_reset_clears():
    d = AlertDedup(ttl_sec=60)
    d.allow("u1", "k", "m")
    d.allow("u2", "k", "m")
    d.reset("u1")
    assert d.allow("u1", "k", "m") is True
    assert d.allow("u2", "k", "m") is False
    d.reset()
    assert d.allow("u2", "k", "m") is True


def test_empty_user_or_kind_pass_through():
    d = AlertDedup(ttl_sec=60)
    assert d.allow("", "k", "m") is True
    assert d.allow("u", "", "m") is True


def test_channel_priority_default():
    d = AlertDedup()
    assert d.select_channel(["inapp", "push", "sms"]) == "push"
    assert d.select_channel(["sms", "email"]) == "sms"
    assert d.select_channel(["email", "inapp"]) == "email"
    assert d.select_channel(["inapp"]) == "inapp"
    assert d.select_channel([]) is None


def test_channel_priority_env_override(monkeypatch):
    monkeypatch.setenv("ALERT_CHANNEL_PRIORITY", "email,push")
    d = AlertDedup()
    assert d.select_channel(["push", "email"]) == "email"
    assert d.select_channel(["sms", "push"]) == "push"
