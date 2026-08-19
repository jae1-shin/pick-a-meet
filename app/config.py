from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "meeting_service"
    database_user: str = "meeting_app"
    database_password: SecretStr = SecretStr("change-me")

    session_secret_key: SecretStr = SecretStr(
        "local-development-secret-change-before-deploy"
    )
    session_timeout_seconds: int = Field(default=28_800, ge=300)
    session_cookie_secure: bool = False

    polling_interval_seconds: int = Field(default=5, ge=1, le=60)
    image_storage_path: Path = Path("./data/uploads")
    image_max_size_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    trusted_proxy: bool = False

    @field_validator("session_secret_key")
    @classmethod
    def validate_session_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET_KEY must be at least 32 characters")
        return value

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
