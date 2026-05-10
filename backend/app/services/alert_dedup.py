"""W8-#5 — 알림 채널 우선순위 + 중복 억제 정책.

같은 사용자에게 짧은 시간 동안 동일 알림이 반복되면 중복으로 간주해 억제.
채널은 우선순위 순으로 단 1개만 발송 (push > sms > email > inapp).

설계 단순화:
- in-memory TTL 캐시 (key=(user_id, kind, hash))
- ``ALERT_DEDUP_TTL_SEC`` env 기본 60초
- ``ALERT_CHANNEL_PRIORITY`` env 콤마 구분 (기본 push,sms,email,inapp)
- ``allow(user_id, kind, message)`` → True 면 발송, False 면 억제
- ``select_channel(available)`` → 우선순위 순으로 첫 매칭 채널 반환
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


_DEFAULT_PRIORITY = ("push", "sms", "email", "inapp")


def _parse_priority() -> tuple[str, ...]:
    raw = os.environ.get("ALERT_CHANNEL_PRIORITY", "")
    if not raw:
        return _DEFAULT_PRIORITY
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts or _DEFAULT_PRIORITY


@dataclass
class _Entry:
    expires_at: float


class AlertDedup:
    def __init__(self, ttl_sec: int | None = None) -> None:
        self._ttl = ttl_sec if ttl_sec is not None else _env_int("ALERT_DEDUP_TTL_SEC", 60)
        self._lock = threading.Lock()
        self._cache: dict[str, _Entry] = {}

    @staticmethod
    def _key(user_id: str, kind: str, message: str) -> str:
        h = hashlib.md5(f"{kind}|{message}".encode()).hexdigest()[:12]
        return f"{user_id}|{kind}|{h}"

    def _gc(self, now: float) -> None:
        # cheap GC — 만료 항목 제거
        expired = [k for k, v in self._cache.items() if v.expires_at <= now]
        for k in expired:
            self._cache.pop(k, None)

    def allow(self, user_id: str, kind: str, message: str) -> bool:
        """발송 가능 여부. True 면 즉시 등록 (= 다음 호출은 차단)."""
        if not user_id or not kind:
            return True
        now = time.time()
        key = self._key(user_id, kind, message or "")
        with self._lock:
            self._gc(now)
            entry = self._cache.get(key)
            if entry is not None and entry.expires_at > now:
                return False
            self._cache[key] = _Entry(expires_at=now + self._ttl)
            return True

    def reset(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._cache.clear()
                return
            for k in list(self._cache.keys()):
                if k.startswith(f"{user_id}|"):
                    self._cache.pop(k, None)

    def select_channel(self, available: list[str]) -> str | None:
        """우선순위 순으로 첫 매칭 채널 반환. 없으면 None."""
        if not available:
            return None
        avail_lower = {c.lower() for c in available}
        for ch in _parse_priority():
            if ch in avail_lower:
                return ch
        return None


alert_dedup = AlertDedup()
