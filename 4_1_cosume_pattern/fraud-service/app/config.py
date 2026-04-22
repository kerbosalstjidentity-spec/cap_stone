from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # .env 키 이름과 명시적으로 맞춤 (두 폴더 연결 시 혼동 방지)
    model_path: str | None = Field(default=None, validation_alias="MODEL_PATH")
    capstone_outputs_dir: str | None = Field(
        default=None,
        validation_alias="CAPSTONE_OUTPUTS_DIR",
    )
    log_level: str = "info"


settings = Settings()
