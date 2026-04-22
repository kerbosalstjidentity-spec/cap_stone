"""Redis 캐시 클라이언트 — 소비 프로필, 리더보드 TTL 캐싱."""

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client = None


async def get_redis():
    """Redis 클라이언트 싱글턴 반환. 연결 실패 시 None 반환 (캐시 우회)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis
        _redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        await _redis_client.ping()
        logger.info("[Redis] Connected to %s", settings.REDIS_URL)
    except Exception as e:
        logger.warning("[Redis] Unavailable (%s) — cache disabled", e)
        _redis_client = None
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    r = await get_redis()
    if not r:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


async def cache_delete(key: str) -> None:
    r = await get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


async def cache_delete_pattern(pattern: str) -> None:
    """패턴 매칭 키 일괄 삭제 (예: 'profile:user123:*')."""
    r = await get_redis()
    if not r:
        return
    try:
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Pub/Sub — 실시간 알림용
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def publish(channel: str, data: Any) -> bool:
    """Redis 채널에 JSON 메시지 발행."""
    r = await get_redis()
    if not r:
        return False
    try:
        await r.publish(channel, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.warning("[Redis] Publish failed: %s", e)
        return False


async def get_pubsub():
    """Redis PubSub 객체 반환 (패턴 구독용)."""
    r = await get_redis()
    if not r:
        return None
    try:
        return r.pubsub()
    except Exception:
        return None
