"""
사용자별 거래 히스토리 인메모리 저장소.

나중에 Redis 교체 시 ProfileStore 인터페이스만 맞추면 됨.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TxRecord:
    tx_id: str
    amount: float
    timestamp: datetime
    merchant_id: str = ""
    device_id: str = ""
    ip: str = ""
    is_foreign_ip: bool = False
    hour: int = -1  # -1 = 미지정, 0~23


@dataclass
class UserProfile:
    user_id: str
    tx_count: int = 0
    total_amount: float = 0.0
    avg_amount: float = 0.0
    max_amount: float = 0.0
    peak_hour: int = -1           # 가장 많이 거래한 시간대
    merchant_diversity: int = 0   # 고유 merchant 수
    velocity: dict[str, int] = field(default_factory=lambda: {"1m": 0, "5m": 0, "15m": 0})


_MAX_HISTORY = 500  # 사용자당 최대 보관 건수


class InMemoryProfileStore:
    """스레드 세이프 인메모리 프로파일 저장소."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # user_id → deque[TxRecord]
        self._history: dict[str, deque[TxRecord]] = defaultdict(lambda: deque(maxlen=_MAX_HISTORY))

    def ingest(self, user_id: str, tx: dict[str, Any]) -> None:
        ts_raw = tx.get("timestamp")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                ts = datetime.now(tz=timezone.utc)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.now(tz=timezone.utc)

        record = TxRecord(
            tx_id=str(tx.get("tx_id", "")),
            amount=float(tx.get("amount", 0.0)),
            timestamp=ts,
            merchant_id=str(tx.get("merchant_id", "")),
            device_id=str(tx.get("device_id", "")),
            ip=str(tx.get("ip", "")),
            is_foreign_ip=bool(tx.get("is_foreign_ip", False)),
            hour=int(tx.get("hour", ts.hour)),
        )
        with self._lock:
            self._history[user_id].append(record)

    def get_profile(self, user_id: str) -> UserProfile | None:
        with self._lock:
            history = list(self._history.get(user_id, []))
        if not history:
            return None

        total = sum(r.amount for r in history)
        count = len(history)
        hour_counts: dict[int, int] = defaultdict(int)
        for r in history:
            if r.hour >= 0:
                hour_counts[r.hour] += 1
        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else -1
        merchants = {r.merchant_id for r in history if r.merchant_id}

        profile = UserProfile(
            user_id=user_id,
            tx_count=count,
            total_amount=total,
            avg_amount=total / count,
            max_amount=max(r.amount for r in history),
            peak_hour=peak_hour,
            merchant_diversity=len(merchants),
            velocity=self._calc_velocity(history),
        )
        return profile

    def get_velocity(self, user_id: str, window_minutes: int) -> int:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            history = list(self._history.get(user_id, []))
        count = 0
        for r in history:
            ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
            delta = (now - ts).total_seconds() / 60
            if delta <= window_minutes:
                count += 1
        return count

    def delete(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._history:
                del self._history[user_id]
                return True
        return False

    def _calc_velocity(self, history: list[TxRecord]) -> dict[str, int]:
        now = datetime.now(tz=timezone.utc)
        result = {"1m": 0, "5m": 0, "15m": 0}
        for r in history:
            ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
            delta = (now - ts).total_seconds() / 60
            if delta <= 1:
                result["1m"] += 1
            if delta <= 5:
                result["5m"] += 1
            if delta <= 15:
                result["15m"] += 1
        return result


import os as _os

def _build_store():
    backend = _os.getenv("PROFILE_STORE", "memory").lower()
    if backend == "redis":
        try:
            from app.services.profile_store_redis import RedisProfileStore
            return RedisProfileStore()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Redis ProfileStore 초기화 실패, InMemory로 fallback: %s", e)
    return InMemoryProfileStore()

# 싱글턴 — PROFILE_STORE=redis 환경변수로 Redis 전환
profile_store = _build_store()
