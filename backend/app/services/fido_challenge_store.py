"""FIDO2 / WebAuthn 챌린지 스토어 — Redis-backed, 인메모리 폴백.

W2-#1: 3개로 분산되어 있던 인메모리 dict (`_registration_challenges`,
`_authentication_challenges`, `_login_challenges`)을 단일 인터페이스로 통합.

키 네임스페이스:
  fido:ch:{scope}:{key}
  - scope: register | auth | login
  - key: register/auth → user_id, login → pre_auth_token

TTL: 5분 (WebAuthn 챌린지 표준 권장).

Redis 미가용 시 프로세스 메모리 dict로 폴백 (싱글 인스턴스에 한해 동작).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Literal

from app.db.redis import get_redis

logger = logging.getLogger(__name__)

Scope = Literal["register", "auth", "login"]
DEFAULT_TTL_S = 300

# 인메모리 폴백 (Redis 미가용 시) — (value, expires_at)
_local_store: dict[str, tuple[bytes, float]] = {}
_local_lock = asyncio.Lock()


def _key(scope: Scope, key: str) -> str:
    return f"fido:ch:{scope}:{key}"


def _now() -> float:
    return time.time()


async def set_challenge(scope: Scope, key: str, challenge: bytes, ttl_s: int = DEFAULT_TTL_S) -> None:
    """챌린지 저장. Redis 우선, 폴백은 프로세스 메모리."""
    full_key = _key(scope, key)
    encoded = base64.b64encode(challenge).decode("ascii")
    r = await get_redis()
    if r is not None:
        try:
            await r.set(full_key, encoded, ex=ttl_s)
            return
        except Exception as e:
            logger.warning("[fido-ch] Redis set 실패, in-memory 폴백: %s", e)
    async with _local_lock:
        _local_store[full_key] = (challenge, _now() + ttl_s)


async def pop_challenge(scope: Scope, key: str) -> bytes | None:
    """챌린지 조회 + 즉시 삭제 (1회용). 없거나 만료 시 None."""
    full_key = _key(scope, key)
    r = await get_redis()
    if r is not None:
        try:
            encoded = await r.getdel(full_key)
            if encoded:
                if isinstance(encoded, bytes):
                    encoded = encoded.decode("ascii")
                return base64.b64decode(encoded)
            # Redis 가용이지만 키 없음 — 폴백 store도 비어있을 가능성 높지만 한번 확인
        except Exception as e:
            logger.warning("[fido-ch] Redis getdel 실패, in-memory 확인: %s", e)
    async with _local_lock:
        entry = _local_store.pop(full_key, None)
    if not entry:
        return None
    value, expires_at = entry
    if _now() > expires_at:
        return None
    return value


async def clear_expired_local() -> int:
    """프로세스 메모리 폴백의 만료 항목 정리 (테스트/유지보수용)."""
    removed = 0
    async with _local_lock:
        now = _now()
        for k in list(_local_store.keys()):
            if _local_store[k][1] < now:
                del _local_store[k]
                removed += 1
    return removed


__all__ = ["DEFAULT_TTL_S", "clear_expired_local", "pop_challenge", "set_challenge"]
