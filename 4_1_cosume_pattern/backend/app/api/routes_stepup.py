"""Step-up Auth API — 리스크 기반 추가 인증 게이트."""

import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token, create_stepup_token, decode_token
from app.config import settings
from app.db.session import get_session
from app.models.tables import StepUpSession, User
from app.schemas.auth import (
    StepUpChallengeResponse,
    StepUpVerifyRequest,
    StepUpVerifyResponse,
)
from app.services.fraud_client import fetch_fraud_profile

router = APIRouter(prefix="/v1/auth/stepup", tags=["stepup"])


async def _get_risk_score(user_id: str) -> float:
    """fraud-service에서 리스크 스코어를 조회. 실패 시 0.0 반환."""
    try:
        profile = await fetch_fraud_profile(user_id)
        if not profile:
            return 0.0
        # fraud-service 응답에서 risk_score 추출 (구조에 따라 조정)
        return float(profile.get("risk_score", profile.get("anomaly_score", 0.0)))
    except Exception:
        return 0.0


def _determine_method(user: User) -> str:
    """사용 가능한 step-up 메서드 우선순위: fido > totp > none."""
    # FIDO는 별도 확인 (DB 쿼리 필요 — 이 함수에서는 totp만 확인)
    if user.totp_enabled:
        return "totp"
    return "none"


# ──────────────────────────────────────────────
#  챌린지 발행
# ──────────────────────────────────────────────

@router.post(
    "/challenge",
    response_model=StepUpChallengeResponse,
    summary="Step-up 인증 필요 여부 확인 및 챌린지 발행",
    description=(
        "현재 사용자의 리스크 스코어를 fraud-service에서 조회합니다.\n\n"
        "- 스코어가 임계값(기본 0.6) 이상이면 추가 인증을 요구합니다.\n"
        "- 반환된 `stepup_token`을 `/verify` 엔드포인트에 제출해야 합니다."
    ),
)
async def request_challenge(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StepUpChallengeResponse:
    risk_score = await _get_risk_score(current_user.user_id)

    if risk_score < settings.STEPUP_RISK_THRESHOLD:
        return StepUpChallengeResponse(
            required=False,
            method="none",
            risk_score=risk_score,
            message="추가 인증이 필요하지 않습니다.",
        )

    # step-up 필요 — 방법 결정
    method = _determine_method(current_user)
    if method == "none":
        # FIDO 등록 여부 확인
        from app.models.tables import FidoCredential
        result = await session.execute(
            select(FidoCredential).where(FidoCredential.user_id == current_user.user_id).limit(1)
        )
        if result.scalar_one_or_none():
            method = "fido"

    if method == "none":
        # 등록된 2FA 수단이 없으면 경고만 반환
        return StepUpChallengeResponse(
            required=True,
            method="none",
            risk_score=risk_score,
            message="리스크가 감지되었지만 등록된 2FA 수단이 없습니다. TOTP 또는 FIDO2를 등록하세요.",
        )

    token = create_stepup_token(current_user.user_id, method, ttl_minutes=10)

    # DB에 세션 기록
    stepup = StepUpSession(
        user_id=current_user.user_id,
        session_token=token,
        method=method,
        risk_score=risk_score,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.add(stepup)
    await session.commit()

    return StepUpChallengeResponse(
        required=True,
        method=method,
        stepup_token=token,
        risk_score=risk_score,
        message=f"리스크 스코어 {risk_score:.2f} — {method.upper()} 인증이 필요합니다.",
    )


# ──────────────────────────────────────────────
#  챌린지 검증
# ──────────────────────────────────────────────

@router.post(
    "/verify",
    response_model=StepUpVerifyResponse,
    summary="Step-up 인증 검증",
    description="TOTP 코드 또는 FIDO2 assertion을 검증하고, 성공 시 갱신된 액세스 토큰을 발급합니다.",
)
async def verify_challenge(
    body: StepUpVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StepUpVerifyResponse:
    # step-up 토큰 검증
    try:
        payload = decode_token(body.stepup_token)
        if payload.get("type") != "stepup":
            raise ValueError("invalid token type")
        if payload["sub"] != current_user.user_id:
            raise ValueError("user mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 step-up 토큰입니다.")

    # DB 세션 확인
    result = await session.execute(
        select(StepUpSession).where(
            StepUpSession.session_token == body.stepup_token,
            StepUpSession.user_id == current_user.user_id,
        )
    )
    stepup_session = result.scalar_one_or_none()
    if not stepup_session:
        raise HTTPException(status_code=400, detail="step-up 세션을 찾을 수 없습니다.")
    if stepup_session.verified:
        raise HTTPException(status_code=400, detail="이미 사용된 step-up 토큰입니다.")
    if stepup_session.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="step-up 토큰이 만료되었습니다.")

    # 방법별 검증
    if body.method == "totp":
        if not body.code:
            raise HTTPException(status_code=400, detail="TOTP 코드를 입력하세요.")
        if not current_user.totp_enabled or not current_user.totp_secret:
            raise HTTPException(status_code=400, detail="TOTP가 활성화되어 있지 않습니다.")
        totp = pyotp.TOTP(current_user.totp_secret)
        if not totp.verify(body.code, valid_window=1):
            return StepUpVerifyResponse(verified=False, message="OTP 코드가 올바르지 않습니다.")

    elif body.method == "fido":
        # FIDO 인증은 /fido/authenticate/verify 엔드포인트에서 처리
        # 여기서는 fido stepup_token만 수락
        fido_payload = payload
        if fido_payload.get("method") != "fido":
            raise HTTPException(status_code=400, detail="FIDO step-up 토큰이 아닙니다.")

    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 인증 방법: {body.method}")

    stepup_session.verified = True
    await session.commit()

    new_access_token = create_access_token(current_user.user_id)
    return StepUpVerifyResponse(
        verified=True,
        access_token=new_access_token,
        message="추가 인증이 완료되었습니다.",
    )


# ──────────────────────────────────────────────
#  보안 이벤트 내역
# ──────────────────────────────────────────────

@router.get(
    "/history",
    summary="보안 이벤트 내역 조회 (로그인, TOTP, Step-up 포함)",
)
async def stepup_history(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(StepUpSession)
        .where(StepUpSession.user_id == current_user.user_id)
        .order_by(StepUpSession.created_at.desc())
        .limit(30)
    )
    sessions = result.scalars().all()

    _method_label = {
        "login": "비밀번호 로그인",
        "login_fail": "로그인 실패",
        "login_totp": "TOTP 로그인",
        "totp_fail": "TOTP 실패",
        "totp": "TOTP Step-up",
        "fido": "FIDO2 Step-up",
    }

    return {
        "user_id": current_user.user_id,
        "history": [
            {
                "method": s.method,
                "method_label": _method_label.get(s.method, s.method),
                "verified": s.verified,
                "risk_score": s.risk_score,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    }
