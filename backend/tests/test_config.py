import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ROOT_DIR, Settings

STRONG_SECRET = "x" * 48


def make_settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": STRONG_SECRET,
        "APP_ENV": "development",
        "APP_DEBUG": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_debug_defaults_to_off(monkeypatch) -> None:
    monkeypatch.delenv("APP_DEBUG", raising=False)
    settings = Settings(_env_file=None, DATABASE_URL="sqlite://", JWT_SECRET_KEY=STRONG_SECRET)
    assert settings.app_debug is False


@pytest.mark.parametrize(
    "secret", ["short", "generate-a-long-random-secret-here"]
)
def test_production_rejects_weak_jwt_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        make_settings(APP_ENV="production", JWT_SECRET_KEY=secret)


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="APP_DEBUG"):
        make_settings(APP_ENV="production", APP_DEBUG=True)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="BACKEND_CORS_ORIGINS"):
        make_settings(APP_ENV="production", BACKEND_CORS_ORIGINS="*")


def test_development_allows_weak_secret() -> None:
    assert make_settings(JWT_SECRET_KEY="short").jwt_secret_key == "short"


def test_relative_storage_path_resolves_against_repo_root() -> None:
    settings = make_settings(STORAGE_BASE_PATH="backend/storage")
    assert settings.storage_root == (ROOT_DIR / "backend" / "storage").resolve()


def test_absolute_storage_path_is_kept(tmp_path: Path) -> None:
    settings = make_settings(STORAGE_BASE_PATH=str(tmp_path))
    assert settings.storage_root == tmp_path.resolve()
