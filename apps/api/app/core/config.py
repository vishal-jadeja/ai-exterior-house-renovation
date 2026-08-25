"""Application settings. Everything comes from the environment; nothing is hard-coded."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = "dev"
    app_name: str = "renovation-api"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://renov:renov@localhost:5433/renov"

    # Auth
    jwt_secret: str = Field(default="change-me-in-production-please", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False  # True in prod (HTTPS)
    cookie_domain: str | None = None

    # CORS
    cors_origins_csv: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    # Object storage (S3-compatible: MinIO locally, Cloudflare R2 in cloud)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None  # browser-reachable endpoint for presigned URLs
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "renovation"
    s3_region: str = "auto"
    presign_ttl_seconds: int = 900

    # Upload limits
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_dimension: int = 4096
    min_image_dimension: int = 640

    # AI providers (all optional; missing key => tier disabled)
    segmentation_model: str = "nvidia/segformer-b2-finetuned-ade-512-512"
    segmentation_enabled: bool = True
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    cf_account_id: str | None = None
    cf_api_token: str | None = None
    fal_key: str | None = None
    render_provider_order_csv: str = Field(
        default="fal,cloudflare,local", alias="RENDER_PROVIDER_ORDER"
    )

    # Worker
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 3

    @property
    def cors_origins(self) -> list[str]:
        return _csv(self.cors_origins_csv)

    @property
    def render_provider_order(self) -> list[str]:
        return _csv(self.render_provider_order_csv)

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
