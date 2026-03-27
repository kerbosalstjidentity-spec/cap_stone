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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
