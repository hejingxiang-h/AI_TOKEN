from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

Port = Annotated[int, Field(ge=1, le=65535)]
Timeout = Annotated[float, Field(gt=0, le=30)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )

    app_name: str = "AI Token Gateway"
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    app_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    app_docs_enabled: bool = True
    app_probe_timeout: Timeout = 2.0
    app_jwt_secret: SecretStr | None = None
    app_access_token_seconds: Annotated[int, Field(ge=60, le=1800)] = 900
    app_refresh_token_seconds: Annotated[int, Field(ge=300, le=2592000)] = 604800
    app_secure_cookies: bool = True
    app_litellm_url: HttpUrl | None = None
    app_litellm_admin_key: SecretStr | None = None

    app_db_host: str = "127.0.0.1"
    app_db_port: Port = 5432
    app_db_name: str = "ai_token_gateway"
    app_db_user: str = "gateway_app"
    app_db_password: SecretStr | None = None

    app_redis_host: str = "127.0.0.1"
    app_redis_port: Port = 6379
    app_redis_db: Annotated[int, Field(ge=0)] = 0
    app_redis_username: str = "default"
    redis_password: SecretStr | None = None

    @property
    def sqlalchemy_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.app_db_user,
            password=self.app_db_password.get_secret_value() if self.app_db_password else None,
            host=self.app_db_host,
            port=self.app_db_port,
            database=self.app_db_name,
        )
