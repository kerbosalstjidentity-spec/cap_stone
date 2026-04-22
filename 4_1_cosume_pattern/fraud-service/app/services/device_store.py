"""
디바이스 핑거프린팅 저장소.

device_id → 최근 N분 내 사용한 user_id 집합 추적.
같은 device_id로 여러 user_id가 거래하면 계정 공유 / 탈취 의심.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

_WINDOW_MINUTES = 60
_MAX_PER_DEVICE = 500


@dataclass
class DeviceRecord:
    user_id: str
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class DeviceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # device_id → deque[DeviceRecord]
        self._data: dict[str, deque[DeviceRecord]] = defaultdict(lambda: deque(maxlen=_MAX_PER_DEVICE))

    def record(self, device_id: str, user_id: str) -> None:
        if not device_id or not user_id:
            return
        rec = DeviceRecord(user_id=user_id)
        with self._lock:
            self._data[device_id].append(rec)

    def unique_users_in_window(self, device_id: str, window_minutes: int = _WINDOW_MINUTES) -> set[str]:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
        with self._lock:
            records = list(self._data.get(device_id, []))
        return {r.user_id for r in records if r.ts >= cutoff}


device_store = DeviceStore()
