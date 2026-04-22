"""FIDO2 / WebAuthn API — 생체인증·하드웨어 보안키 등록 및 인증."""

import base64
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import settings
from app.db.session import get_session
from app.models.tables import FidoCredential, User

try:
    import webauthn
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorAttestationResponse,
        AuthenticatorAssertionResponse,
        AuthenticatorSelectionCriteria,
        AuthenticationCredential,
        PublicKeyCredentialDescriptor,
        RegistrationCredential,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    _WEBAUTHN_AVAILABLE = True
except ImportError:
    _WEBAUTHN_AVAILABLE = False

router = APIRouter(prefix="/v1/auth/fido", tags=["fido2"])

# 인메모리 챌린지 임시 저장 (프로덕션에서는 Redis 사용)
_registration_challenges: dict[str, bytes] = {}
_authentication_challenges: dict[str, bytes] = {}


def _check_webauthn():
    if not _WEBAUTHN_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="py_webauthn 라이브러리가 설치되지 않았습니다. pip install py_webauthn",
        )


# ──────────────────────────────────────────────
#  스키마
# ──────────────────────────────────────────────

class RegistrationOptionsResponse(BaseModel):
    challenge: str
    rp_id: str
    rp_name: str
    user_id: str
    user_name: str
    timeout: int = 60000


class RegistrationVerifyRequest(BaseModel):
    credential_id: str
    client_data_json: str
    attestation_object: str
    device_name: str = "내 인증 장치"


class AuthenticationOptionsResponse(BaseModel):
    challenge: str
    rp_id: str
    timeout: int = 60000
    allow_credentials: list[dict]


class AuthenticationVerifyRequest(BaseModel):
    credential_id: str
    client_data_json: str
    authenticator_data: str
    signature: str


class CredentialInfo(BaseModel):
    id: int
    credential_id_prefix: str   # 식별용 앞 12자
    name: str
    device_type: str
    aaguid: str
    last_used_at: str | None
    created_at: str


# ──────────────────────────────────────────────
#  등록 (Registration)
# ──────────────────────────────────────────────

@router.get(
    "/register/options",
    response_model=RegistrationOptionsResponse,
    summary="FIDO2 등록 옵션 생성",
    description="WebAuthn credential 등록 시작. 클라이언트가 이 challenge를 사용해 authenticator를 호출합니다.",
)
async def registration_options(
    current_user: User = Depends(get_current_user),
) -> RegistrationOptionsResponse:
    _check_webauthn()

    options = webauthn.generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=current_user.user_id.encode(),
        user_name=current_user.email or current_user.user_id,
        user_display_name=current_user.nickname or current_user.user_id,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _registration_challenges[current_user.user_id] = options.challenge

    return RegistrationOptionsResponse(
        challenge=bytes_to_base64url(options.challenge),
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=current_user.user_id,
        user_name=current_user.email or current_user.user_id,
    )


@router.post(
    "/register/verify",
    summary="FIDO2 등록 완료",
    description="authenticator가 반환한 attestation을 검증하고 credential을 저장합니다.",
)
async def registration_verify(
    body: RegistrationVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _check_webauthn()

    expected_challenge = _registration_challenges.pop(current_user.user_id, None)
    if not expected_challenge:
        raise HTTPException(status_code=400, detail="등록 챌린지가 없거나 만료되었습니다.")

    try:
        verification = webauthn.verify_registration_response(
            credential=RegistrationCredential(
                id=body.credential_id,
                raw_id=base64url_to_bytes(body.credential_id),
                response=AuthenticatorAttestationResponse(
                    client_data_json=base64url_to_bytes(body.client_data_json),
                    attestation_object=base64url_to_bytes(body.attestation_object),
                ),
            ),
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"FIDO2 등록 실패: {e}")

    # 중복 credential 확인
    existing = await session.execute(
        select(FidoCredential).where(FidoCredential.credential_id == body.credential_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="이미 등록된 인증 장치입니다.")

    cred = FidoCredential(
        user_id=current_user.user_id,
        credential_id=body.credential_id,
        public_key=base64.b64encode(verification.credential_public_key).decode(),
        sign_count=verification.sign_count,
        aaguid=str(verification.aaguid) if verification.aaguid else "",
        name=body.device_name,
    )
    session.add(cred)
    await session.commit()

    return {"status": "registered", "credential_id_prefix": body.credential_id[:12]}


# ──────────────────────────────────────────────
#  인증 (Authentication)
# ──────────────────────────────────────────────

@router.get(
    "/authenticate/options",
    response_model=AuthenticationOptionsResponse,
    summary="FIDO2 인증 옵션 생성",
)
async def authentication_options(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuthenticationOptionsResponse:
    _check_webauthn()

    result = await session.execute(
        select(FidoCredential).where(FidoCredential.user_id == current_user.user_id)
    )
    creds = result.scalars().all()
    if not creds:
        raise HTTPException(status_code=404, detail="등록된 FIDO2 인증 장치가 없습니다.")

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in creds
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _authentication_challenges[current_user.user_id] = options.challenge

    return AuthenticationOptionsResponse(
        challenge=bytes_to_base64url(options.challenge),
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[{"id": c.credential_id, "name": c.name} for c in creds],
    )


@router.post(
    "/authenticate/verify",
    summary="FIDO2 인증 완료 및 Step-up 토큰 발급",
)
async def authentication_verify(
    body: AuthenticationVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _check_webauthn()

    expected_challenge = _authentication_challenges.pop(current_user.user_id, None)
    if not expected_challenge:
        raise HTTPException(status_code=400, detail="인증 챌린지가 없거나 만료되었습니다.")

    result = await session.execute(
        select(FidoCredential).where(
            FidoCredential.user_id == current_user.user_id,
            FidoCredential.credential_id == body.credential_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="인증 장치를 찾을 수 없습니다.")

    try:
        verification = webauthn.verify_authentication_response(
            credential=AuthenticationCredential(
                id=body.credential_id,
                raw_id=base64url_to_bytes(body.credential_id),
                response=AuthenticatorAssertionResponse(
                    client_data_json=base64url_to_bytes(body.client_data_json),
                    authenticator_data=base64url_to_bytes(body.authenticator_data),
                    signature=base64url_to_bytes(body.signature),
                ),
            ),
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=base64.b64decode(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"FIDO2 인증 실패: {e}")

    cred.sign_count = verification.new_sign_count
    cred.last_used_at = datetime.now(UTC)
    await session.commit()

    from app.auth.jwt import create_stepup_token
    stepup_token = create_stepup_token(current_user.user_id, "fido", ttl_minutes=15)

    return {"verified": True, "stepup_token": stepup_token}


# ──────────────────────────────────────────────
#  등록 장치 관리
# ──────────────────────────────────────────────

@router.get(
    "/credentials",
    response_model=list[CredentialInfo],
    summary="등록된 FIDO2 장치 목록",
)
async def list_credentials(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CredentialInfo]:
    result = await session.execute(
        select(FidoCredential).where(FidoCredential.user_id == current_user.user_id)
    )
    creds = result.scalars().all()
    return [
        CredentialInfo(
            id=c.id,
            credential_id_prefix=c.credential_id[:12],
            name=c.name,
            device_type=c.device_type,
            aaguid=c.aaguid,
            last_used_at=c.last_used_at.isoformat() if c.last_used_at else None,
            created_at=c.created_at.isoformat(),
        )
        for c in creds
    ]


@router.delete(
    "/credentials/{credential_db_id}",
    summary="FIDO2 장치 삭제",
)
async def delete_credential(
    credential_db_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(FidoCredential).where(
            FidoCredential.id == credential_db_id,
            FidoCredential.user_id == current_user.user_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="인증 장치를 찾을 수 없습니다.")
    await session.delete(cred)
    await session.commit()
    return {"status": "deleted"}


# ──────────────────────────────────────────────
#  로그인용 FIDO2 인증 (pre_auth_token 기반)
# ──────────────────────────────────────────────

class FidoLoginOptionsRequest(BaseModel):
    pre_auth_token: str


class FidoLoginOptionsResponse(BaseModel):
    challenge: str
    rp_id: str
    timeout: int = 60000
    allow_credentials: list[dict]


class FidoLoginVerifyRequest(BaseModel):
    pre_auth_token: str
    credential_id: str
    client_data_json: str
    authenticator_data: str
    signature: str


# 로그인용 챌린지 임시 저장 (pre_auth_token → challenge)
_login_challenges: dict[str, bytes] = {}


@router.post(
    "/login/options",
    response_model=FidoLoginOptionsResponse,
    summary="로그인용 FIDO2 챌린지 발급 (비밀번호 인증 후 호출)",
)
async def fido_login_options(
    body: FidoLoginOptionsRequest,
    session: AsyncSession = Depends(get_session),
) -> FidoLoginOptionsResponse:
    _check_webauthn()

    # pre_auth_token 검증
    from app.auth.jwt import decode_token
    try:
        payload = decode_token(body.pre_auth_token)
        if payload.get("type") != "pre_auth":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")

    result = await session.execute(
        select(FidoCredential).where(FidoCredential.user_id == user_id)
    )
    creds = result.scalars().all()
    if not creds:
        raise HTTPException(status_code=404, detail="등록된 FIDO2 장치가 없습니다.")

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in creds
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    # pre_auth_token을 키로 챌린지 저장
    _login_challenges[body.pre_auth_token] = options.challenge

    return FidoLoginOptionsResponse(
        challenge=bytes_to_base64url(options.challenge),
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[{"id": c.credential_id, "name": c.name} for c in creds],
    )


@router.post(
    "/login/verify",
    summary="로그인용 FIDO2 assertion 검증 → 액세스 토큰 발급",
)
async def fido_login_verify(
    body: FidoLoginVerifyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    _check_webauthn()

    # pre_auth_token 검증
    from app.auth.jwt import decode_token, create_access_token, create_refresh_token
    try:
        payload = decode_token(body.pre_auth_token)
        if payload.get("type") != "pre_auth":
            raise ValueError("invalid token type")
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")

    expected_challenge = _login_challenges.pop(body.pre_auth_token, None)
    if not expected_challenge:
        raise HTTPException(status_code=400, detail="챌린지가 없거나 만료되었습니다. 다시 시도하세요.")

    # credential 조회
    result = await session.execute(
        select(FidoCredential).where(
            FidoCredential.user_id == user_id,
            FidoCredential.credential_id == body.credential_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="인증 장치를 찾을 수 없습니다.")

    try:
        verification = webauthn.verify_authentication_response(
            credential=AuthenticationCredential(
                id=body.credential_id,
                raw_id=base64url_to_bytes(body.credential_id),
                response=AuthenticatorAssertionResponse(
                    client_data_json=base64url_to_bytes(body.client_data_json),
                    authenticator_data=base64url_to_bytes(body.authenticator_data),
                    signature=base64url_to_bytes(body.signature),
                ),
            ),
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=base64.b64decode(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"FIDO2 인증 실패: {e}")

    cred.sign_count = verification.new_sign_count
    cred.last_used_at = datetime.now(UTC)

    # 사용자 last_login_at 갱신
    from app.models.tables import User
    user_result = await session.execute(select(User).where(User.user_id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.last_login_at = datetime.now(UTC)

    await session.commit()

    # 보안 이벤트 기록
    import secrets as _secrets
    from datetime import timedelta
    from app.models.tables import StepUpSession
    event = StepUpSession(
        user_id=user_id,
        session_token=f"evt_{_secrets.token_hex(16)}",
        method="login_fido",
        verified=True,
        risk_score=0.0,
        expires_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    session.add(event)
    await session.commit()

    return {
        "verified": True,
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "user_id": user_id,
        "nickname": user.nickname if user else "",
    }
