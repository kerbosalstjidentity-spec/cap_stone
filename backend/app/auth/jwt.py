"""JWT 토큰 생성·검증 + jti 블랙리스트 (Redis 기반)."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.db.redis import get_redis

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  비밀번호
# ──────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ──────────────────────────────────────────────
#  토큰 생성 (jti 포함)
# ──────────────────────────────────────────────

def _new_jti() -> str:
    return secrets.token_urlsafe(16)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access", "jti": _new_jti()}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "type": "refresh", "jti": _new_jti()}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """토큰 디코딩. 유효하지 않으면 JWTError를 raise."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def create_stepup_token(user_id: str, method: str, ttl_minutes: int = 10) -> str:
    """Step-up 인증용 단기 토큰."""
    expire = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    payload = {"sub": user_id, "exp": expire, "type": "stepup", "method": method, "jti": _new_jti()}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_pre_auth_token(user_id: str) -> str:
    """로그인 1단계 완료 후 TOTP 인증 대기용 단기 토큰 (5분)."""
    expire = datetime.now(UTC) + timedelta(minutes=5)
    payload = {"sub": user_id, "exp": expire, "type": "pre_auth", "jti": _new_jti()}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ──────────────────────────────────────────────
#  jti 블랙리스트 (W1-#2)
# ──────────────────────────────────────────────
#
#  운영 정책:
#  - 로그아웃 시 access + refresh의 jti를 모두 블랙리스트 등록
#  - 계정 잠금/비활성화 시 사용자의 모든 활성 토큰 무효화
#  - 키: `jwt:bl:{jti}` (값: 1, TTL: 토큰 남은 수명)
#  - Redis 미가용 시 fail-open (로그 경고만) — 가용성 vs 보안 트레이드오프
#    실제 운영에서는 fail-close로 전환 가능 (BLACKLIST_FAIL_CLOSED env)

_BL_KEY_PREFIX = "jwt:bl:"


async def blacklist_jti(jti: str, ttl_seconds: int) -> bool:
    """jti를 블랙리스트에 추가. TTL은 토큰 남은 수명."""
    if not jti or ttl_seconds <= 0:
        return False
    r = await get_redis()
    if not r:
        logger.warning("[JWT-BL] Redis 미가용 — jti 블랙리스트 등록 실패: %s", jti[:8])
        return False
    try:
        await r.set(f"{_BL_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)
        return True
    except Exception as e:
        logger.warning("[JWT-BL] 등록 실패: %s", e)
        return False


async def is_jti_blacklisted(jti: str) -> bool:
    """jti가 블랙리스트에 있는지 확인. Redis 미가용 시 False(fail-open)."""
    if not jti:
        return False
    r = await get_redis()
    if not r:
        return False
    try:
        return bool(await r.exists(f"{_BL_KEY_PREFIX}{jti}"))
    except Exception:
        return False


def remaining_ttl_seconds(payload: dict) -> int:
    """토큰 payload의 exp에서 남은 TTL(초) 계산. 만료/오류 시 0."""
    exp = payload.get("exp")
    if not exp:
        return 0
    try:
        exp_dt = datetime.fromtimestamp(int(exp), tz=UTC)
        delta = (exp_dt - datetime.now(UTC)).total_seconds()
        return max(0, int(delta))
    except Exception:
        return 0


__all__ = [
    "JWTError",
    "blacklist_jti",
    "create_access_token",
    "create_pre_auth_token",
    "create_refresh_token",
    "create_stepup_token",
    "decode_token",
    "hash_password",
    "is_jti_blacklisted",
    "remaining_ttl_seconds",
    "verify_password",
]
