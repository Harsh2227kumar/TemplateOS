from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = Field(default="TemplateOS API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    backend_cors_origins: str = Field(
        default="http://localhost:5173", alias="BACKEND_CORS_ORIGINS"
    )
    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    storage_base_path: str = Field(default="backend/storage", alias="STORAGE_BASE_PATH")
    # --- AI (V1.3 Phase 4): AWS Bedrock via AnthropicBedrock ---
    # None -> AI features stay off (503 "not configured") until the team sets it.
    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    # Claude Sonnet on Bedrock (model routing: suggestions). Cross-region
    # inference profile id — verify the exact id in the team's AWS account.
    bedrock_model_suggestions: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        alias="BEDROCK_MODEL_SUGGESTIONS",
    )
    ai_max_output_tokens: int = Field(default=1024, alias="AI_MAX_OUTPUT_TOKENS")

    @property
    def ai_is_configured(self) -> bool:
        """
        True when Bedrock could actually be called: a region is set AND AWS
        credentials are resolvable (env vars, or boto3's default chain:
        profile file / instance role). Cheap, network-free, and never raises.
        """
        if not self.aws_region:
            return False
        import os

        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get(
            "AWS_SECRET_ACCESS_KEY"
        ):
            return True
        try:
            from boto3.session import Session

            return Session(region_name=self.aws_region).get_credentials() is not None
        except Exception:
            return False

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
