from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "consume-pattern"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/consume_pattern"
    REDIS_URL: str = "redis://localhost:6379/1"

    # fraud-service 연계
    FRAUD_SERVICE_URL: str = "http://localhost:8010"

    # capstone 모델 경로
    CAPSTONE_MODEL_PATH: str = ""
    CAPSTONE_OUTPUTS_DIR: str = ""

    # ML 설정
    ANOMALY_THRESHOLD: float = -0.5
    OVERSPEND_THRESHOLD: float = 0.7
    CLUSTER_COUNT: int = 4

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8020

    # JWT Auth
    # HS256 (대칭) — 기본값, 단일 백엔드 환경
    JWT_SECRET_KEY: str = "consume-pattern-super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"  # "HS256" 또는 "RS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # RS256 (비대칭, 다중 서비스 검증용) — 활성화 시 JWT_ALGORITHM="RS256"
    # JWT_RSA_PRIVATE_KEY_PEM: 발급 서명용 (서비스 1대만 보관)
    # JWT_RSA_PUBLIC_KEYS_JSON: {"<kid>": "<PEM>"} — 검증 측에서 kid로 키 선택
    # JWT_ACTIVE_KID: 현재 서명에 사용할 kid (회전 시 새 kid로 변경, 이전 kid는 검증용으로 유지)
    JWT_RSA_PRIVATE_KEY_PEM: str = ""
    JWT_RSA_PUBLIC_KEYS_JSON: str = "{}"
    JWT_ACTIVE_KID: str = ""

    # WebAuthn / FIDO2
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "Consume Pattern"
    WEBAUTHN_ORIGIN: str = "http://localhost:3020"

    # Step-up Auth (fraud-service 리스크 임계값)
    STEPUP_RISK_THRESHOLD: float = 0.6   # 이 이상이면 추가 인증 요구

    # Redis 캐시 TTL (초)
    CACHE_TTL_SPEND_PROFILE: int = 300   # 5분
    CACHE_TTL_LEADERBOARD: int = 60      # 1분

    # 알림 시스템
    NOTIFICATION_RETENTION_DAYS: int = 30
    BUDGET_WARNING_THRESHOLD: float = 0.8  # 예산 80% 도달 시 경고

    # XAI
    SHAP_MAX_SAMPLES: int = 1000

    # 감정 분석
    EMOTION_RISK_THRESHOLD: float = 0.6

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
