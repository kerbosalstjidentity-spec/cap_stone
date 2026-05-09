"""
사용자별 거래 히스토리 인메모리 저장소.

나중에 Redis 교체 시 ProfileStore 인터페이스만 맞추면 됨.

W2-#7: velocity 계산을 O(log N + W) 로 최적화.
- 히스토리는 시간순 append-only deque → 맨 앞부터 만료 항목 pop
- bisect 로 윈도우 시작 인덱스를 이진 탐색해 카운트 = len - idx
- 매 요청 선형 순회 → amortized O(1) (각 record 는 최대 한 번만 만료 pop)
- Redis 백엔드(profile_store_redis.py) 는 sorted set 사용으로 O(log N + W) 보장
"""

from __future__ import annotations

import bisect
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
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
    # W7.5-#3: 사용자 시간대 활동 분포 (0~23 → 거래 건수). OffHoursClusterRule 입력.
    hour_histogram: dict[int, int] = field(default_factory=dict)


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
            hour_histogram=dict(hour_counts),
        )
        return profile

    def _prune_expired(self, user_id: str, max_window_minutes: int = 60) -> None:
        """W2-#7: 가장 큰 윈도우(60분)보다 오래된 record 만료 — amortized O(1).

        velocity 윈도우는 1m/5m/15m 이지만 NewMerchantRule 등이 60m 까지 사용 가능하므로
        여유 있게 60m 보존. 락은 호출자에서 잡고 있어야 한다.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=max_window_minutes)
        dq = self._history.get(user_id)
        if dq is None:
            return
        while dq:
            ts = dq[0].timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                dq.popleft()
            else:
                break

    @staticmethod
    def _count_within(history: list[TxRecord], window_minutes: int) -> int:
        """history 가 timestamp 오름차순으로 정렬돼 있다는 가정 하에 bisect 로 O(log N) 카운트."""
        if not history:
            return 0
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
        ts_list = [
            (r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc))
            for r in history
        ]
        # 정렬되어 있다고 가정 — bisect_left 가 O(log N)
        idx = bisect.bisect_left(ts_list, cutoff)
        return len(ts_list) - idx

    def get_velocity(self, user_id: str, window_minutes: int) -> int:
        with self._lock:
            self._prune_expired(user_id)
            history = list(self._history.get(user_id, []))
        return self._count_within(history, window_minutes)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._history:
                del self._history[user_id]
                return True
        return False

    def _calc_velocity(self, history: list[TxRecord]) -> dict[str, int]:
        # W2-#7: bisect 기반 카운트 — 각 윈도우 O(log N)
        return {
            "1m": self._count_within(history, 1),
            "5m": self._count_within(history, 5),
            "15m": self._count_within(history, 15),
        }


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
