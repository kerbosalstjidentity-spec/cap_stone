"""
디바이스 핑거프린팅 저장소.

device_id → 최근 N분 내 사용한 user_id 집합 추적.
같은 device_id로 여러 user_id가 거래하면 계정 공유 / 탈취 의심.

W2-#3: Redis sorted set + TTL 기반으로 멀티 인스턴스 공유 가능.
- 키: device:users:{device_id}
- 멤버: user_id, 점수: epoch timestamp
- ZRANGEBYSCORE 로 윈도우 조회 (O(log N + M))
- 키 자체에 TTL — 일정 시간 미사용 device_id 는 자동 만료
- Redis 미가용 시 threading.Lock + deque 폴백 (싱글 인스턴스)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

try:
    import redis as redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
_WINDOW_MINUTES = 60
_MAX_PER_DEVICE = 500
_KEY_PREFIX = "device:users:"
_KEY_TTL_S = int(os.getenv("DEVICE_STORE_TTL_S", str(2 * _WINDOW_MINUTES * 60)))  # 2시간 기본

_redis_client = None


def _get_redis():
    global _redis_client
    if not _HAS_REDIS or not REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
        logger.info("[device-store] Redis 연결 성공")
    except Exception as e:
        logger.warning("[device-store] Redis 연결 실패, in-memory 폴백: %s", e)
        _redis_client = None
    return _redis_client


@dataclass
class DeviceRecord:
    user_id: str
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class DeviceStore:
    """Redis sorted set + 인메모리 폴백."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 폴백 — device_id → deque[DeviceRecord]
        self._data: dict[str, deque[DeviceRecord]] = defaultdict(lambda: deque(maxlen=_MAX_PER_DEVICE))

    def _key(self, device_id: str) -> str:
        return f"{_KEY_PREFIX}{device_id}"

    def record(self, device_id: str, user_id: str) -> None:
        if not device_id or not user_id:
            return
        now_ts = time.time()
        r = _get_redis()
        if r is not None:
            try:
                key = self._key(device_id)
                pipe = r.pipeline()
                # member 는 "user_id|ts" 로 유니크 보장 (동일 user_id 의 다중 기록 허용)
                pipe.zadd(key, {f"{user_id}|{now_ts}": now_ts})
                # 윈도우 밖 항목 정리
                cutoff = now_ts - (_WINDOW_MINUTES * 60)
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.expire(key, _KEY_TTL_S)
                pipe.execute()
                return
            except Exception as e:
                logger.warning("[device-store] Redis zadd 실패, 폴백: %s", e)

        rec = DeviceRecord(user_id=user_id)
        with self._lock:
            self._data[device_id].append(rec)

    def unique_users_in_window(self, device_id: str, window_minutes: int = _WINDOW_MINUTES) -> set[str]:
        if not device_id:
            return set()
        now_ts = time.time()
        cutoff = now_ts - (window_minutes * 60)

        r = _get_redis()
        if r is not None:
            try:
                members = r.zrangebyscore(self._key(device_id), cutoff, now_ts)
                # member 형식 "user_id|ts" → user_id 추출
                return {m.rsplit("|", 1)[0] for m in members}
            except Exception as e:
                logger.warning("[device-store] Redis zrangebyscore 실패, 폴백: %s", e)

        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
        with self._lock:
            records = list(self._data.get(device_id, []))
        return {r.user_id for r in records if r.ts >= cutoff_dt}


device_store = DeviceStore()
