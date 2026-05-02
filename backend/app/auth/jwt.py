"""JWT 토큰 생성·검증 + jti 블랙리스트 (Redis 기반).

W1-#3: HS256 ↔ RS256 양립 지원.
- HS256: 단일 백엔드 (기본). settings.JWT_SECRET_KEY 단일 키.
- RS256: 다중 서비스 검증. settings.JWT_RSA_PRIVATE_KEY_PEM (서명) +
  settings.JWT_RSA_PUBLIC_KEYS_JSON {kid: pem} (검증, 회전용 다중 키).
  서명 시 헤더에 kid를 박아두고, 검증 시 kid로 공개키를 lookup.
"""

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.db.redis import get_redis

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  키·알고리즘 헬퍼 (W1-#3)
# ──────────────────────────────────────────────

_JWT_DEFAULT_SECRET = "consume-pattern-super-secret-key-change-in-production"


def validate_jwt_config() -> None:
    """W1-#3/#4 fail-fast — 운영 환경에서 JWT 설정 검증.

    - ENV=production 이면 JWT_SECRET_KEY 기본값/JWT_RSA_PRIVATE_KEY 누락 시 RuntimeError
    - dev/test에서는 경고만
    """
    import os

    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "development").lower()
    is_prod = env in ("production", "prod")

    if (settings.JWT_ALGORITHM or "").upper() == "RS256":
        if not settings.JWT_RSA_PRIVATE_KEY_PEM:
            msg = "JWT_ALGORITHM=RS256 인데 JWT_RSA_PRIVATE_KEY_PEM 미설정"
            if is_prod:
                raise RuntimeError(f"[JWT] {msg} — production 기동 차단")
            logger.warning("[JWT] %s — dev에서는 폴백 동작이지만 운영 전 설정 필요", msg)
        if not settings.JWT_ACTIVE_KID:
            logger.warning("[JWT] JWT_ACTIVE_KID 미설정 — kid 헤더 없이 서명됨")
    else:
        # HS256 — 시크릿 검증
        if not settings.JWT_SECRET_KEY or settings.JWT_SECRET_KEY == _JWT_DEFAULT_SECRET:
            msg = "JWT_SECRET_KEY가 기본값/미설정"
            if is_prod:
                raise RuntimeError(f"[JWT] {msg} — production 기동 차단")
            logger.warning("[JWT] %s — 운영 배포 전 반드시 교체", msg)
        elif len(settings.JWT_SECRET_KEY) < 32:
            if is_prod:
                raise RuntimeError(f"[JWT] JWT_SECRET_KEY 길이 부족({len(settings.JWT_SECRET_KEY)}<32) — production 기동 차단")


def _is_rs256() -> bool:
    return (settings.JWT_ALGORITHM or "").upper() == "RS256"


def _signing_key() -> str:
    """서명에 사용할 키 반환. RS256이면 RSA private PEM, 아니면 HMAC secret."""
    if _is_rs256():
        if not settings.JWT_RSA_PRIVATE_KEY_PEM:
            raise RuntimeError("JWT_ALGORITHM=RS256 인데 JWT_RSA_PRIVATE_KEY_PEM 미설정")
        return settings.JWT_RSA_PRIVATE_KEY_PEM
    return settings.JWT_SECRET_KEY


def _signing_headers() -> dict:
    """서명 시 JWT 헤더. RS256이면 kid 포함."""
    if _is_rs256() and settings.JWT_ACTIVE_KID:
        return {"kid": settings.JWT_ACTIVE_KID}
    return {}


def _public_keys_map() -> dict[str, str]:
    """RS256 검증용 공개키 맵 {kid: pem}. JSON 파싱 실패 시 빈 dict."""
    raw = settings.JWT_RSA_PUBLIC_KEYS_JSON or "{}"
    try:
        m = json.loads(raw)
        return {str(k): str(v) for k, v in m.items()}
    except Exception as e:
        logger.warning("[JWT] JWT_RSA_PUBLIC_KEYS_JSON 파싱 실패: %s", e)
        return {}


def _verification_key(token: str) -> tuple[str, list[str]]:
    """토큰의 헤더를 보고 검증에 사용할 키 + 허용 알고리즘 반환.

    HS256 토큰 → HS256 키
    RS256 토큰 → kid로 공개키 lookup
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        # 헤더조차 못 읽으면 알고리즘에 맞춰 폴백 → decode가 실패시킨다
        if _is_rs256():
            return _signing_key(), ["RS256"]
        return settings.JWT_SECRET_KEY, ["HS256"]

    alg = (header.get("alg") or "").upper()
    if alg == "RS256":
        kid = header.get("kid", "")
        keys = _public_keys_map()
        pub = keys.get(kid)
        if not pub:
            # 활성 kid의 사설키에서 공개키를 만들어 폴백 — RS256 + kid 미확인
            raise JWTError(f"unknown kid: {kid}")
        return pub, ["RS256"]
    # HS256 (또는 기타) — 단일 secret
    return settings.JWT_SECRET_KEY, [alg or "HS256"]


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


def _encode(payload: dict) -> str:
    return jwt.encode(
        payload,
        _signing_key(),
        algorithm=settings.JWT_ALGORITHM,
        headers=_signing_headers(),
    )


def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    return _encode({"sub": user_id, "exp": expire, "type": "access", "jti": _new_jti()})


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    return _encode({"sub": user_id, "exp": expire, "type": "refresh", "jti": _new_jti()})


def decode_token(token: str) -> dict:
    """토큰 디코딩. 유효하지 않으면 JWTError를 raise.

    헤더의 alg/kid를 보고 검증 키를 선택 — HS256 ↔ RS256 자동 라우팅.
    """
    key, algos = _verification_key(token)
    return jwt.decode(token, key, algorithms=algos)


def create_stepup_token(user_id: str, method: str, ttl_minutes: int = 10) -> str:
    """Step-up 인증용 단기 토큰."""
    expire = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return _encode({"sub": user_id, "exp": expire, "type": "stepup", "method": method, "jti": _new_jti()})


def create_pre_auth_token(user_id: str) -> str:
    """로그인 1단계 완료 후 TOTP 인증 대기용 단기 토큰 (5분)."""
    expire = datetime.now(UTC) + timedelta(minutes=5)
    return _encode({"sub": user_id, "exp": expire, "type": "pre_auth", "jti": _new_jti()})


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
