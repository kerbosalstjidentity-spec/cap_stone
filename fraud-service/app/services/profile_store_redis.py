"""
Redis 기반 ProfileStore.

PROFILE_STORE=redis 환경변수 설정 시 InMemory 대신 이 구현체를 사용.
redis-py >= 4.0 (sync 버전) 필요.

키 전략:
  profile:{user_id}:meta   → Hash (tx_count, total_amount, ...)
  profile:{user_id}:hist   → Sorted Set (score=timestamp, value=JSON 거래 레코드)
  TTL: PROFILE_TTL_SEC (기본 7일)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

try:
    import redis as redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

from app.services.profile_store import UserProfile, TxRecord

REDIS_URL       = os.getenv("REDIS_URL", "redis://localhost:6379/0")
PROFILE_TTL_SEC = int(os.getenv("PROFILE_TTL_SEC", str(7 * 24 * 3600)))
_MAX_HIST       = 500


class RedisProfileStore:
    """
    redis-py StrictRedis 래퍼.
    InMemoryProfileStore와 동일한 public 인터페이스:
      ingest(), get_profile(), get_velocity(), delete()
    """

    def __init__(self) -> None:
        if not _HAS_REDIS:
            raise RuntimeError("redis-py 미설치. pip install redis")
        self._r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    # ------------------------------------------------------------------
    def ingest(self, user_id: str, tx: dict[str, Any]) -> None:
        ts_raw = tx.get("timestamp")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                ts = datetime.now(tz=timezone.utc)
        else:
            ts = datetime.now(tz=timezone.utc)
        score_ts = ts.timestamp()

        hist_key = f"profile:{user_id}:hist"
        meta_key = f"profile:{user_id}:meta"

        pipe = self._r.pipeline()

        # Sorted Set에 거래 추가 (score = unix timestamp)
        record = {
            "tx_id": tx.get("tx_id", ""),
            "amount": float(tx.get("amount", 0)),
            "merchant_id": tx.get("merchant_id", ""),
            "device_id": tx.get("device_id", ""),
            "ip": tx.get("ip", ""),
            "is_foreign_ip": tx.get("is_foreign_ip", False),
            "hour": tx.get("hour", ts.hour),
            "ts": score_ts,
        }
        pipe.zadd(hist_key, {json.dumps(record): score_ts})
        # 최대 보관 건수 유지 (오래된 것 제거)
        pipe.zremrangebyrank(hist_key, 0, -(_MAX_HIST + 1))

        # meta 카운터 업데이트
        pipe.hincrbyfloat(meta_key, "total_amount", float(tx.get("amount", 0)))
        pipe.hincrby(meta_key, "tx_count", 1)

        pipe.expire(hist_key, PROFILE_TTL_SEC)
        pipe.expire(meta_key, PROFILE_TTL_SEC)
        pipe.execute()

    def get_profile(self, user_id: str) -> UserProfile | None:
        hist_key = f"profile:{user_id}:hist"
        raw_list = self._r.zrange(hist_key, 0, -1)
        if not raw_list:
            return None

        records = [json.loads(r) for r in raw_list]
        count = len(records)
        total = sum(r["amount"] for r in records)

        from collections import defaultdict
        hour_counts: dict[int, int] = defaultdict(int)
        merchants = set()
        for r in records:
            h = r.get("hour", -1)
            if h >= 0:
                hour_counts[h] += 1
            m = r.get("merchant_id", "")
            if m:
                merchants.add(m)

        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else -1

        return UserProfile(
            user_id=user_id,
            tx_count=count,
            total_amount=total,
            avg_amount=total / count,
            max_amount=max(r["amount"] for r in records),
            peak_hour=peak_hour,
            merchant_diversity=len(merchants),
            velocity=self._calc_velocity_from_records(records),
        )

    def get_velocity(self, user_id: str, window_minutes: int) -> int:
        hist_key = f"profile:{user_id}:hist"
        now = time.time()
        min_score = now - window_minutes * 60
        return self._r.zcount(hist_key, min_score, "+inf")

    def delete(self, user_id: str) -> bool:
        pipe = self._r.pipeline()
        pipe.delete(f"profile:{user_id}:hist")
        pipe.delete(f"profile:{user_id}:meta")
        results = pipe.execute()
        return any(results)

    # ------------------------------------------------------------------
    def _calc_velocity_from_records(self, records: list[dict]) -> dict[str, int]:
        now = time.time()
        result = {"1m": 0, "5m": 0, "15m": 0}
        for r in records:
            delta = (now - r["ts"]) / 60
            if delta <= 1:
                result["1m"] += 1
            if delta <= 5:
                result["5m"] += 1
            if delta <= 15:
                result["15m"] += 1
        return result
