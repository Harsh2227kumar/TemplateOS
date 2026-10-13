from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()
# Verified against when the user does not exist, so a failed login costs the
# same hashing time either way and response timing does not reveal accounts.
_DUMMY_PASSWORD_HASH = password_hash.hash("templateos-dummy-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        password_hash.verify(password, _DUMMY_PASSWORD_HASH)
        return False
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": subject, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> str:
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("Token subject is missing")
    return subject


# --- Cookie sessions -------------------------------------------------------
# Contract shared with the frontend; see app/api/v1/endpoints/auth.py.
ACCESS_COOKIE_NAME = "templateos_access"
REFRESH_COOKIE_NAME = "templateos_refresh"
# The refresh cookie is only ever sent to the auth endpoints.
REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"
CSRF_HEADER_NAME = "X-Requested-With"
CSRF_HEADER_VALUE = "TemplateOS"


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
    }


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        **_cookie_options(),
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        **_cookie_options(),
    )


def clear_auth_cookies(response: Response) -> None:
    # Attributes must match the ones used when setting, or browsers keep them.
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", **_cookie_options())
    response.delete_cookie(
        REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, **_cookie_options()
    )
