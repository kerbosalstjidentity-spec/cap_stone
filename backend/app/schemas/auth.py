"""인증 관련 Pydantic 스키마."""

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str
    age: int | None = None
    occupation: str = ""
    monthly_income: float | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    nickname: str


class LoginResponse(BaseModel):
    """로그인 응답 — 2FA 없으면 즉시 토큰, 있으면 2단계 대기."""
    totp_required: bool = False
    fido_available: bool = False        # FIDO2 장치 등록된 경우 True
    pre_auth_token: str | None = None   # 2단계 인증 필요할 때만 반환
    # 2FA 없거나 완료 시 아래 필드 채워짐
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str = ""
    nickname: str = ""


class TotpLoginRequest(BaseModel):
    pre_auth_token: str   # 1단계에서 받은 토큰
    code: str             # Google Authenticator 6자리


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    user_id: str
    email: str | None
    nickname: str
    age: int | None
    occupation: str
    monthly_income: float | None
    edu_level: str
    totp_enabled: bool

    model_config = {"from_attributes": True}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return v


# ──────────────────────────────────────────────
#  TOTP 2FA
# ──────────────────────────────────────────────

class TotpSetupResponse(BaseModel):
    secret: str
    qr_uri: str        # otpauth:// URI
    qr_image: str      # base64 PNG data URL (data:image/png;base64,...)


class TotpVerifyRequest(BaseModel):
    code: str     # 6자리 OTP


# ──────────────────────────────────────────────
#  Step-up Auth
# ──────────────────────────────────────────────

class StepUpChallengeResponse(BaseModel):
    required: bool
    method: str           # "none" | "totp" | "fido"
    stepup_token: str | None = None
    risk_score: float = 0.0
    message: str = ""


class StepUpVerifyRequest(BaseModel):
    stepup_token: str
    method: str           # "totp" | "fido"
    code: str | None = None          # TOTP 코드
    assertion_response: dict | None = None  # FIDO2 assertion


class StepUpVerifyResponse(BaseModel):
    verified: bool
    access_token: str | None = None  # 인증 성공 시 갱신된 액세스 토큰
    message: str = ""
