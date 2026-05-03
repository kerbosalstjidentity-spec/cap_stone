"""인증 API — 회원가입, 로그인, 프로필, TOTP 2FA."""

import base64
import io
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.deps import get_current_user
from app.auth.jwt import (
    blacklist_jti,
    create_access_token,
    create_pre_auth_token,
    create_refresh_token,
    decode_token,
    hash_password,
    remaining_ttl_seconds,
    verify_password,
)
from app.db.session import get_session
from app.models.tables import StepUpSession, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TotpLoginRequest,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserProfile,
)

bearer_scheme = HTTPBearer(auto_error=False)


async def _log_security_event(
    session: AsyncSession,
    user_id: str,
    method: str,
    verified: bool,
    risk_score: float = 0.0,
) -> None:
    """보안 이벤트를 StepUpSession 테이블에 기록."""
    event = StepUpSession(
        user_id=user_id,
        session_token=f"evt_{secrets.token_hex(16)}",
        method=method,
        verified=verified,
        risk_score=risk_score,
        expires_at=datetime.now(UTC) + timedelta(seconds=1),  # 이미 만료된 이벤트 기록용
    )
    session.add(event)
    await session.commit()

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
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
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

    # 회원가입 즉시 데모 데이터 시딩 → 대시보드가 바로 보임
    try:
        from app.api.routes_seed import seed_user_data
        await seed_user_data(user_id, session, months=3, tx_per_month=40)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Auto-seed after register failed: %s", e)

    # W4-#5: ML 학습은 BackgroundTasks 로 분리 → 회원가입 응답 지연 제거
    async def _train_in_background() -> None:
        import logging as _lg
        from app.db.session import async_session_factory
        from app.ml.trainer import train_all
        try:
            async with async_session_factory() as bg_session:
                await train_all(bg_session)
        except Exception as e:
            _lg.getLogger(__name__).warning("Auto-train after register failed: %s", e)

    background_tasks.add_task(_train_in_background)

    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
        nickname=user.nickname,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="로그인 (TOTP 활성화 시 2단계 반환)",
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        # 로그인 실패 이벤트 기록 (user가 있을 때만)
        if user:
            await _log_security_event(session, user.user_id, "login_fail", False)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 잘못되었습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    # FIDO2 장치 등록 여부 확인
    from app.models.tables import FidoCredential
    fido_result = await session.execute(
        select(FidoCredential).where(FidoCredential.user_id == user.user_id).limit(1)
    )
    has_fido = fido_result.scalar_one_or_none() is not None

    # 2FA 필요한 경우 (TOTP 또는 FIDO2)
    if user.totp_enabled or has_fido:
        pre_auth_token = create_pre_auth_token(user.user_id)
        return LoginResponse(
            totp_required=user.totp_enabled,
            fido_available=has_fido,
            pre_auth_token=pre_auth_token,
            user_id=user.user_id,
            nickname=user.nickname,
        )

    # 2FA 없음 — 즉시 토큰 발급
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await _log_security_event(session, user.user_id, "login", True)

    return LoginResponse(
        totp_required=False,
        fido_available=False,
        access_token=create_access_token(user.user_id),
        refresh_token=create_refresh_token(user.user_id),
        user_id=user.user_id,
        nickname=user.nickname,
    )


@router.post(
    "/login/totp",
    response_model=LoginResponse,
    summary="로그인 2단계 — TOTP 코드 검증",
)
async def login_totp(body: TotpLoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    """비밀번호 인증 후 TOTP 코드를 검증하고 최종 토큰을 발급합니다."""
    try:
        payload = decode_token(body.pre_auth_token)
        if payload.get("type") != "pre_auth":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP가 활성화되어 있지 않습니다.")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.code, valid_window=1):
        await _log_security_event(session, user.user_id, "totp_fail", False)
        raise HTTPException(status_code=401, detail="OTP 코드가 올바르지 않습니다.")

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await _log_security_event(session, user.user_id, "login_totp", True)

    return LoginResponse(
        totp_required=False,
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
    from app.auth.jwt import is_jti_blacklisted

    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
        old_jti = payload.get("jti")
        old_ttl = remaining_ttl_seconds(payload)
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="유효하지 않은 리프레시 토큰입니다.")

    if old_jti and await is_jti_blacklisted(old_jti):
        raise HTTPException(status_code=401, detail="만료되었거나 폐기된 리프레시 토큰입니다.")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    # refresh 토큰 회전 — 사용된 jti는 블랙리스트로
    if old_jti and old_ttl > 0:
        await blacklist_jti(old_jti, old_ttl)

    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
        nickname=user.nickname,
    )


@router.post(
    "/logout",
    summary="로그아웃 — access/refresh jti 블랙리스트 등록",
)
async def logout(
    body: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """access 토큰의 jti와 (옵션) refresh 토큰의 jti를 블랙리스트에 등록.

    - access: Authorization 헤더의 Bearer 토큰
    - refresh: 요청 body의 refresh_token (옵션)
    - 잘못된 토큰이라도 200 반환 (정보 누출 차단)
    """
    blacklisted = []

    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            jti = payload.get("jti")
            ttl = remaining_ttl_seconds(payload)
            if jti and ttl > 0 and await blacklist_jti(jti, ttl):
                blacklisted.append("access")
        except Exception:
            pass

    if body and body.refresh_token:
        try:
            payload = decode_token(body.refresh_token)
            jti = payload.get("jti")
            ttl = remaining_ttl_seconds(payload)
            if jti and ttl > 0 and await blacklist_jti(jti, ttl):
                blacklisted.append("refresh")
        except Exception:
            pass

    return {"status": "ok", "blacklisted": blacklisted}


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

    # QR 코드 이미지 생성 (PNG → base64 data URL)
    img = qrcode.make(qr_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    return TotpSetupResponse(secret=secret, qr_uri=qr_uri, qr_image=qr_b64)


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  W3-#7: 백업 코드 (패스키/2FA 분실 복구)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from pydantic import BaseModel, Field


class BackupCodesResponse(BaseModel):
    codes: list[str] = Field(default_factory=list)  # 평문, 1회 노출
    count: int


class BackupCodeConsumeRequest(BaseModel):
    code: str


@router.post(
    "/me/backup-codes/regenerate",
    response_model=BackupCodesResponse,
    summary="백업 코드 10개 신규 발급 (기존 모두 무효화)",
)
async def regenerate_backup_codes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BackupCodesResponse:
    """랜덤 16자 백업 코드 10개 발급. 평문은 응답으로 1회 반환, DB에는 bcrypt 해시만 저장."""
    import json as _json
    plain_codes = [secrets.token_urlsafe(12) for _ in range(10)]
    hashed = [hash_password(c) for c in plain_codes]
    current_user.backup_codes_json = _json.dumps(hashed)
    await session.commit()
    return BackupCodesResponse(codes=plain_codes, count=len(plain_codes))


@router.post(
    "/login/backup-code",
    response_model=LoginResponse,
    summary="백업 코드로 2단계 인증 우회 (1회용, 소진 후 제거)",
)
async def login_with_backup_code(
    body: BackupCodeConsumeRequest,
    pre_auth_token: str,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """pre_auth_token 으로 사용자 식별 후 백업 코드 검증 → 토큰 발급."""
    import json as _json
    try:
        payload = decode_token(pre_auth_token)
        if payload.get("type") != "pre_auth":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    try:
        codes_hashed: list[str] = _json.loads(user.backup_codes_json or "[]")
    except Exception:
        codes_hashed = []

    # 일치하는 해시 찾아서 제거 (1회용)
    matched_idx = -1
    for i, h in enumerate(codes_hashed):
        if verify_password(body.code, h):
            matched_idx = i
            break
    if matched_idx < 0:
        await _log_security_event(session, user.user_id, "backup_code_fail", False)
        raise HTTPException(status_code=401, detail="백업 코드가 올바르지 않습니다.")

    codes_hashed.pop(matched_idx)
    user.backup_codes_json = _json.dumps(codes_hashed)
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await _log_security_event(session, user.user_id, "login_backup_code", True)

    return LoginResponse(
        totp_required=False,
        access_token=create_access_token(user.user_id),
        refresh_token=create_refresh_token(user.user_id),
        user_id=user.user_id,
        nickname=user.nickname,
    )


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
