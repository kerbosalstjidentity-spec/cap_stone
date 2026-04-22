"""JWT 토큰 생성·검증 유틸리티."""

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings


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
#  액세스 토큰
# ──────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """토큰 디코딩. 유효하지 않으면 JWTError를 raise."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def create_stepup_token(user_id: str, method: str, ttl_minutes: int = 10) -> str:
    """Step-up 인증용 단기 토큰."""
    expire = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    payload = {"sub": user_id, "exp": expire, "type": "stepup", "method": method}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_pre_auth_token(user_id: str) -> str:
    """로그인 1단계 완료 후 TOTP 인증 대기용 단기 토큰 (5분)."""
    expire = datetime.now(UTC) + timedelta(minutes=5)
    payload = {"sub": user_id, "exp": expire, "type": "pre_auth"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
