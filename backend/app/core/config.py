import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]

logger = logging.getLogger(__name__)

# The placeholder shipped in .env.example; never acceptable outside development.
_EXAMPLE_JWT_SECRET = "generate-a-long-random-secret-here"
_MIN_JWT_SECRET_LENGTH = 32


def _load_ai_env_from_file() -> None:
    """
    Export the AI/Bedrock-related variables from the repository .env into
    os.environ, BEFORE Settings is constructed.

    Why two problems are solved at once:
    1. pydantic-settings gives REAL environment variables priority over the
       .env file. A stale session/Windows variable (e.g. an old
       BEDROCK_MODEL_SUGGESTIONS or another project's AWS_ACCESS_KEY_ID)
       would silently override the values the team set in .env.
    2. The AWS credential vars are deliberately NOT Settings fields — the
       AWS SDK (boto3 / AnthropicBedrock) reads os.environ and its own
       provider chain, so .env values must be exported there to be seen.

    Precedence: for these keys, .env OVERRIDES inherited environment
    variables — the .env file is this project's source of truth for the AI
    configuration and identity. When .env defines none of them, inherited
    values and the standard provider chain apply unchanged.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:  # python-dotenv is a pydantic-settings dependency
        return
    values = dotenv_values(ROOT_DIR / ".env")
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "BEDROCK_MODEL_SUGGESTIONS",
        "BEDROCK_MODEL_NOVA_LITE",
        "BEDROCK_MODEL_NOVA_MICRO",
        "AI_MAX_OUTPUT_TOKENS",
        "AWS_BEARER_TOKEN_BEDROCK",
    ):
        value = values.get(key)
        if value:
            os.environ[key] = value


_load_ai_env_from_file()


class Settings(BaseSettings):
    app_name: str = Field(default="TemplateOS API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    # Off unless explicitly enabled: debug mode returns tracebacks to clients.
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    backend_cors_origins: str = Field(
        default="http://localhost:5173", alias="BACKEND_CORS_ORIGINS"
    )
    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    # Short-lived access JWT (cookie `templateos_access` or Bearer header);
    # sessions are extended through the rotating refresh token.
    access_token_expire_minutes: int = Field(
        default=15, ge=1, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, ge=1, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )
    # None -> Secure follows APP_ENV (on in production, off otherwise so the
    # cookies work over plain http://localhost during development).
    cookie_secure_override: bool | None = Field(default=None, alias="COOKIE_SECURE")
    # None/"" -> host-only cookies (the safest default).
    cookie_domain_setting: str | None = Field(default=None, alias="COOKIE_DOMAIN")
    # In-memory login throttling (per client IP and per email).
    login_rate_limit_enabled: bool = Field(default=True, alias="LOGIN_RATE_LIMIT_ENABLED")
    login_rate_limit_attempts: int = Field(
        default=10, ge=1, alias="LOGIN_RATE_LIMIT_ATTEMPTS"
    )
    login_rate_limit_window_seconds: int = Field(
        default=300, ge=1, alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS"
    )
    # A relative path is resolved against the repository root (see
    # storage_root), so the location does not depend on the working directory.
    storage_base_path: str = Field(default="backend/storage", alias="STORAGE_BASE_PATH")
    # --- AI (V1.3 Phase 4): AWS Bedrock via AnthropicBedrock ---
    # None/"" -> AI features stay off (503 "not configured") until the team
    # sets them. BOTH values come from .env only — no model id or region is
    # hardcoded in code (per V1.3 P4 rule); .env.example documents examples.
    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    # Bedrock model / cross-region inference-profile id — REQUIRED when
    # AWS_REGION is set. Find it in the Bedrock console (Model access).
    bedrock_model_suggestions: str = Field(
        default="",
        alias="BEDROCK_MODEL_SUGGESTIONS",
    )
    # V1.5 Phase 1 text actions (Amazon Nova via the Bedrock Converse API).
    # Same rule: ids come from .env only. In ap-south-1 Nova is invoked via
    # the APAC inference profile, e.g. "apac.amazon.nova-lite-v1:0".
    # Micro handles "grammar"; Lite handles "tone" / "concise" / "formal".
    bedrock_model_nova_lite: str = Field(default="", alias="BEDROCK_MODEL_NOVA_LITE")
    bedrock_model_nova_micro: str = Field(
        default="", alias="BEDROCK_MODEL_NOVA_MICRO"
    )
    ai_max_output_tokens: int = Field(default=1024, alias="AI_MAX_OUTPUT_TOKENS")

    @property
    def ai_is_configured(self) -> bool:
        """
        True when Bedrock could actually be called: region AND model id are
        set AND auth resolves — either a Bedrock long-term API key
        (AWS_BEARER_TOKEN_BEDROCK) or AWS credentials (env vars, or boto3's
        default chain: profile file / instance role). Cheap, network-free,
        never raises.
        """
        if not self.aws_region or not self.bedrock_model_suggestions:
            return False
        if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            return True
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
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def cookie_secure(self) -> bool:
        if self.cookie_secure_override is None:
            return self.is_production
        return self.cookie_secure_override

    @property
    def cookie_domain(self) -> str | None:
        domain = (self.cookie_domain_setting or "").strip()
        return domain or None

    @property
    def storage_root(self) -> Path:
        path = Path(self.storage_base_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path.resolve()

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

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        weak_secret = (
            self.jwt_secret_key == _EXAMPLE_JWT_SECRET
            or len(self.jwt_secret_key) < _MIN_JWT_SECRET_LENGTH
        )
        if self.is_production:
            if weak_secret:
                raise ValueError(
                    "JWT_SECRET_KEY must be a random value of at least "
                    f"{_MIN_JWT_SECRET_LENGTH} characters in production"
                )
            if self.app_debug:
                raise ValueError("APP_DEBUG must be false in production")
            if "*" in self.cors_origins:
                raise ValueError("BACKEND_CORS_ORIGINS must not contain '*' in production")
            if not self.cookie_secure:
                logger.warning(
                    "COOKIE_SECURE is off in production; session cookies will be "
                    "sent over plain HTTP"
                )
        elif weak_secret:
            logger.warning(
                "JWT_SECRET_KEY is the example value or shorter than %d characters; "
                "set a long random secret before deploying",
                _MIN_JWT_SECRET_LENGTH,
            )
        return self

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
