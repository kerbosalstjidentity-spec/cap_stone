"""JWT 인증 API 테스트."""

import uuid

import pytest

pytestmark = pytest.mark.api

_RUN = uuid.uuid4().hex[:8]


def _email(name: str) -> str:
    """테스트 실행마다 고유한 이메일 생성."""
    return f"{name}_{_RUN}@example.com"


def _register(client, email: str, password: str = "pass12345", nickname: str = "테스트"):
    return client.post("/v1/auth/register", json={
        "email": email, "password": password, "nickname": nickname,
    })


def _token(client, email: str, password: str = "pass12345") -> str:
    reg = _register(client, email, password=password)
    if reg.status_code == 201:
        return reg.json()["access_token"]
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    return login.json()["access_token"]


# ──────────────────────────────────────────────
#  회원가입
# ──────────────────────────────────────────────

def test_register_success(api_client):
    resp = _register(api_client, _email("reg_success"), nickname="가입성공")
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["nickname"] == "가입성공"
    assert data["user_id"].startswith("u_")


def test_register_duplicate_email(api_client):
    email = _email("dup")
    _register(api_client, email)
    resp = _register(api_client, email)
    assert resp.status_code == 409


def test_register_short_password(api_client):
    resp = api_client.post("/v1/auth/register", json={
        "email": _email("shortpw"), "password": "short", "nickname": "x",
    })
    assert resp.status_code == 422


# ──────────────────────────────────────────────
#  로그인
# ──────────────────────────────────────────────

def test_login_success(api_client):
    email, pw = _email("login_ok"), "loginpass456"
    _register(api_client, email, password=pw)
    resp = api_client.post("/v1/auth/login", json={"email": email, "password": pw})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert resp.json()["token_type"] == "bearer"


def test_login_wrong_password(api_client):
    email = _email("wrongpw")
    _register(api_client, email, password="correct123")
    resp = api_client.post("/v1/auth/login", json={"email": email, "password": "wrong999"})
    assert resp.status_code == 401


def test_login_unknown_email(api_client):
    resp = api_client.post("/v1/auth/login", json={"email": "nobody@x.com", "password": "any"})
    assert resp.status_code == 401


# ──────────────────────────────────────────────
#  토큰 갱신
# ──────────────────────────────────────────────

def test_refresh_token(api_client):
    reg = _register(api_client, _email("refresh_ok"))
    refresh_token = reg.json()["refresh_token"]
    resp = api_client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_invalid_token(api_client):
    resp = api_client.post("/v1/auth/refresh", json={"refresh_token": "totally.fake.token"})
    assert resp.status_code == 401


# ──────────────────────────────────────────────
#  /me 프로필
# ──────────────────────────────────────────────

def test_get_me_authenticated(api_client):
    email = _email("me_ok")
    token = _token(api_client, email)
    resp = api_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email
    assert data["totp_enabled"] is False


def test_get_me_unauthenticated(api_client):
    resp = api_client.get("/v1/auth/me")
    assert resp.status_code == 401


def test_get_me_bad_token(api_client):
    resp = api_client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


# ──────────────────────────────────────────────
#  비밀번호 변경
# ──────────────────────────────────────────────

def test_change_password(api_client):
    email = _email("changepw")
    token = _token(api_client, email)
    resp = api_client.post(
        "/v1/auth/me/change-password",
        json={"current_password": "pass12345", "new_password": "newpass789"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    login = api_client.post("/v1/auth/login", json={"email": email, "password": "newpass789"})
    assert login.status_code == 200


def test_change_password_wrong_current(api_client):
    token = _token(api_client, _email("wrongcur"))
    resp = api_client.post(
        "/v1/auth/me/change-password",
        json={"current_password": "wrong_old", "new_password": "newpass789"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
