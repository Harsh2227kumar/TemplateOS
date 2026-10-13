"""
Auth endpoints. Browser sessions use httpOnly cookies:

- templateos_access   access JWT, Path=/, Max-Age=ACCESS_TOKEN_EXPIRE_MINUTES
- templateos_refresh  opaque rotating token, Path=/api/v1/auth,
                      Max-Age=REFRESH_TOKEN_EXPIRE_DAYS

both HttpOnly, SameSite=Lax, Secure per COOKIE_SECURE, Domain per
COOKIE_DOMAIN. /login also returns the access token as JSON for scripts and
tests, which may keep using `Authorization: Bearer`. Unsafe cookie requests
need `X-Requested-With: TemplateOS` (app/core/csrf.py).
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    create_access_token,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from app.crud.refresh_token_crud import (
    RotationStatus,
    delete_expired_refresh_tokens,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, Token
from app.schemas.user import UserProfileRead, UserRead

router = APIRouter()


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession) -> User:
    email = payload.email.lower()
    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        hashed_password=hash_password(payload.password),
        role="normal_user",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession
) -> Token:
    email = payload.email.lower()
    client_ip = request.client.host if request.client else None
    limit = login_rate_limiter.check(client_ip, email)
    if not limit.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(limit.retry_after)},
        )

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    hashed_password = user.hashed_password if user is not None else None
    if not verify_password(payload.password, hashed_password) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    delete_expired_refresh_tokens(db)
    refresh = issue_refresh_token(db, user.id)
    db.commit()
    access_token = create_access_token(str(user.id))
    set_auth_cookies(response, access_token, refresh.token)
    return Token(access_token=access_token)


def _unauthorized_clearing_cookies(detail: str) -> JSONResponse:
    # Returned (not raised) so the cookie deletions reach the client.
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
    clear_auth_cookies(response)
    return response


@router.post(
    "/refresh",
    response_model=Token,
    responses={
        401: {"description": "Missing, invalid, expired or reused refresh token"},
        409: {"description": "Token was rotated within the reuse grace window"},
    },
)
def refresh_session(request: Request, response: Response, db: DbSession):
    """
    Rotate the refresh cookie: the presented token is revoked and a new
    access + refresh pair is set. A token rotated within
    REFRESH_REUSE_GRACE_SECONDS (concurrent tabs) gets 409 and nothing
    changes; any other revoked token revokes its whole session family
    (theft signal), clears the cookies and returns 401.
    """
    result = rotate_refresh_token(db, request.cookies.get(REFRESH_COOKIE_NAME))
    if result.status is RotationStatus.ALREADY_ROTATED:
        # Another tab rotated it moments ago and the browser already holds
        # the replacement cookies: leave the session and cookies alone.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Refresh token already rotated"},
        )
    if result.status is RotationStatus.REUSED:
        return _unauthorized_clearing_cookies("Refresh token reuse detected")
    if result.status is not RotationStatus.ROTATED or result.issued is None:
        return _unauthorized_clearing_cookies("Invalid refresh token")

    user_id = result.issued.record.user_id
    if db.get(User, user_id) is None:
        return _unauthorized_clearing_cookies("Invalid refresh token")
    access_token = create_access_token(str(user_id))
    set_auth_cookies(response, access_token, result.issued.token)
    return Token(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: DbSession) -> Response:
    """
    Revoke the presented refresh token (if any) and clear both cookies.
    Needs no valid access token, so it works after the access JWT expired.
    """
    revoke_refresh_token(db, request.cookies.get(REFRESH_COOKIE_NAME))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserProfileRead)
def my_profile(current_user: CurrentUser) -> User:
    return current_user
