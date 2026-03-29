"""인증 API — 회원가입, 로그인, 프로필, TOTP 2FA."""

import secrets
import uuid
from datetime import UTC, datetime

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_session
from app.models.tables import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserProfile,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  회원가입 / 로그인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    summary="회원가입",
)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    # 이메일 중복 확인
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    user_id = f"u_{uuid.uuid4().hex[:12]}"
    user = User(
        user_id=user_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        nickname=body.nickname,
        age=body.age,
        occupation=body.occupation,
        monthly_income=body.monthly_income,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
        nickname=user.nickname,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인",
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 잘못되었습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    user.last_login_at = datetime.now(UTC)
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.user_id),
        refresh_token=create_refresh_token(user.user_id),
        user_id=user.user_id,
        nickname=user.nickname,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="액세스 토큰 갱신",
)
async def refresh_token(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="유효하지 않은 리프레시 토큰입니다.")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
        nickname=user.nickname,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  프로필
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/me",
    response_model=UserProfile,
    summary="내 프로필 조회",
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserProfile,
    summary="프로필 수정",
)
async def update_me(
    body: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    allowed = {"nickname", "age", "occupation", "monthly_income"}
    for key, value in body.items():
        if key in allowed:
            setattr(current_user, key, value)
    await session.commit()
    await session.refresh(current_user)
    return UserProfile.model_validate(current_user)


@router.post(
    "/me/change-password",
    summary="비밀번호 변경",
)
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not current_user.hashed_password or not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    current_user.hashed_password = hash_password(body.new_password)
    await session.commit()
    return {"status": "ok", "message": "비밀번호가 변경되었습니다."}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOTP 2FA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/me/totp/setup",
    response_model=TotpSetupResponse,
    summary="TOTP 2FA 설정 시작",
    description="Google Authenticator 등 OTP 앱으로 스캔할 QR URI를 반환합니다.",
)
async def totp_setup(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TotpSetupResponse:
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    await session.commit()

    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(
        name=current_user.email or current_user.user_id,
        issuer_name="Consume Pattern",
    )
    return TotpSetupResponse(secret=secret, qr_uri=qr_uri)


@router.post(
    "/me/totp/verify",
    summary="TOTP 코드 확인 및 2FA 활성화",
)
async def totp_verify(
    body: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="먼저 TOTP 설정을 시작하세요 (/totp/setup).")
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="OTP 코드가 올바르지 않습니다.")
    current_user.totp_enabled = True
    await session.commit()
    return {"status": "ok", "totp_enabled": True}


@router.post(
    "/me/totp/disable",
    summary="TOTP 2FA 비활성화",
)
async def totp_disable(
    body: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP가 활성화되어 있지 않습니다.")
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="OTP 코드가 올바르지 않습니다.")
    current_user.totp_enabled = False
    current_user.totp_secret = None
    await session.commit()
    return {"status": "ok", "totp_enabled": False}
