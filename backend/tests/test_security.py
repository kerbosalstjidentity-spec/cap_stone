"""JWT 토큰 유틸 및 보안 로직 단위 테스트 (서버 불필요)."""

import time

import pytest
from jose import JWTError

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    create_stepup_token,
    decode_token,
    hash_password,
    verify_password,
)


# ──────────────────────────────────────────────
#  비밀번호 해싱
# ──────────────────────────────────────────────

def test_hash_and_verify():
    plain = "mypassword123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_wrong_password_rejected():
    hashed = hash_password("correct")
    assert not verify_password("incorrect", hashed)


def test_same_password_different_hash():
    """bcrypt는 salt를 사용하므로 동일 평문도 매번 다른 해시."""
    pw = "same_password"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2
    assert verify_password(pw, h1)
    assert verify_password(pw, h2)


# ──────────────────────────────────────────────
#  JWT 토큰 생성·검증
# ──────────────────────────────────────────────

def test_access_token_contains_user_id():
    token = create_access_token("user_abc")
    payload = decode_token(token)
    assert payload["sub"] == "user_abc"
    assert payload["type"] == "access"


def test_refresh_token_type():
    token = create_refresh_token("user_xyz")
    payload = decode_token(token)
    assert payload["type"] == "refresh"


def test_stepup_token_has_method():
    token = create_stepup_token("user_123", "totp", ttl_minutes=5)
    payload = decode_token(token)
    assert payload["type"] == "stepup"
    assert payload["method"] == "totp"
    assert payload["sub"] == "user_123"


def test_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_tampered_token_raises():
    token = create_access_token("user_safe")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_token(tampered)


def test_access_token_not_valid_as_refresh():
    """액세스 토큰을 리프레시 토큰으로 쓸 수 없어야 한다 — type 체크는 라우터에서 수행."""
    token = create_access_token("user_check")
    payload = decode_token(token)
    assert payload["type"] == "access"
    assert payload["type"] != "refresh"


# ──────────────────────────────────────────────
#  설정 검증
# ──────────────────────────────────────────────

def test_config_jwt_defaults():
    from app.config import settings
    assert settings.JWT_ACCESS_EXPIRE_MINUTES > 0
    assert settings.JWT_REFRESH_EXPIRE_DAYS > 0
    assert len(settings.JWT_SECRET_KEY) >= 16
    assert settings.JWT_ALGORITHM == "HS256"


def test_config_stepup_threshold():
    from app.config import settings
    assert 0.0 <= settings.STEPUP_RISK_THRESHOLD <= 1.0


def test_config_cache_ttl():
    from app.config import settings
    assert settings.CACHE_TTL_SPEND_PROFILE > 0
    assert settings.CACHE_TTL_LEADERBOARD > 0


def test_config_webauthn():
    from app.config import settings
    assert settings.WEBAUTHN_RP_ID != ""
    assert settings.WEBAUTHN_RP_NAME != ""
    assert settings.WEBAUTHN_ORIGIN.startswith("http")
