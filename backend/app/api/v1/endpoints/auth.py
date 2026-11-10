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

import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
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
    get_by_token,
    RotationStatus,
    delete_expired_refresh_tokens,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.core.config import settings
from app.models.user import User
from app.services import audit_service, eklink
from app.schemas.auth import (
    EklinkCallbackRequest,
    EklinkConfig,
    LoginRequest,
    SignupRequest,
    Token,
)
from app.schemas.user import UserProfileRead, UserRead, UserSelfUpdate

router = APIRouter()


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession) -> User:
    if not settings.allow_public_signup:
        raise HTTPException(
            status_code=403,
            detail="Self sign-up is turned off. Sign in with EkLink or ask an administrator.",
        )
    email = payload.email.lower()
    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        hashed_password=hash_password(payload.password),
        role="student",
        member_type="student",
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
        # The submitted email only: never the password.
        audit_service.record_and_commit(
            db,
            request,
            actor=None,
            actor_email=email[:255],
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user is not None else None,
            summary="Failed login",
            organization_id=user.organization_id if user is not None else None,
            department_id=user.department_id if user is not None else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact your administrator.",
        )

    delete_expired_refresh_tokens(db)
    refresh = issue_refresh_token(db, user.id)
    audit_service.record(
        db, request, actor=user, action="auth.login", entity_type="user", entity_id=user.id, summary="Signed in"
    )
    db.commit()
    access_token = create_access_token(str(user.id))
    set_auth_cookies(response, access_token, refresh.token)
    return Token(access_token=access_token)


EKLINK_STATE_COOKIE_PATH = f"{settings.api_v1_prefix}/auth/eklink"


def _eklink_state_cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": EKLINK_STATE_COOKIE_PATH,
    }


@router.get("/eklink", response_model=EklinkConfig)
def eklink_config() -> EklinkConfig:
    """Whether "Sign in with EkLink" is available (public, no secrets)."""
    signup_enabled = settings.allow_public_signup
    if not settings.eklink_enabled:
        return EklinkConfig(enabled=False, signup_enabled=signup_enabled)
    return EklinkConfig(
        enabled=True, eklink_url=settings.eklink_url, signup_enabled=signup_enabled
    )


@router.get("/eklink/login", include_in_schema=False)
def eklink_login() -> RedirectResponse:
    """Browser navigation: remember a random state and go to EkLink's /authorize."""
    if not settings.eklink_enabled:
        raise HTTPException(status_code=404, detail="EkLink sign-in is not configured")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(eklink.authorize_url(state), status_code=302)
    response.set_cookie(
        eklink.STATE_COOKIE_NAME,
        state,
        max_age=eklink.STATE_MAX_AGE_SECONDS,
        **_eklink_state_cookie_options(),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/eklink/callback", response_model=Token)
def eklink_callback(
    payload: EklinkCallbackRequest, request: Request, response: Response, db: DbSession
) -> Token:
    """
    The SPA's /auth/callback posts EkLink's code and state here. The state
    must match the cookie set by /eklink/login (one use: the cookie is
    cleared either way).
    """
    if not settings.eklink_enabled:
        raise HTTPException(status_code=404, detail="EkLink sign-in is not configured")
    response.delete_cookie(eklink.STATE_COOKIE_NAME, **_eklink_state_cookie_options())
    expected_state = request.cookies.get(eklink.STATE_COOKIE_NAME) or ""
    if not expected_state or not secrets.compare_digest(expected_state, payload.state):
        raise HTTPException(
            status_code=400, detail="The sign-in request expired. Please try again."
        )

    try:
        claims = eklink.verify_token(eklink.exchange_code(payload.code))
        user = eklink.sync_user(db, claims)
    except eklink.EklinkError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    delete_expired_refresh_tokens(db)
    refresh = issue_refresh_token(db, user.id)
    audit_service.record(
        db,
        request,
        actor=user,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        summary="Signed in with EkLink",
        details={"method": "eklink"},
    )
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
    user = db.get(User, user_id)
    if user is None or not user.is_active:
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
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    record = get_by_token(db, token)
    user = db.get(User, record.user_id) if record is not None else None
    revoke_refresh_token(db, token)
    if user is not None:
        audit_service.record_and_commit(
            db, request, actor=user, action="auth.logout", entity_type="user", entity_id=user.id,
            summary="Signed out",
        )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserProfileRead)
def my_profile(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/me", response_model=UserProfileRead)
def update_my_profile(
    payload: UserSelfUpdate, current_user: CurrentUser, db: DbSession
) -> User:
    """
    Self-service profile edit: full_name, phone and job_title only. Role,
    organization and department are managed by administrators
    (/admin/users); sending them (or any other field) is a 422. For
    EkLink-linked users the name comes from EkLink: changing it is a 409.
    """
    changes = payload.model_dump(exclude_unset=True)
    if (
        current_user.eklink_sub
        and "full_name" in changes
        and changes["full_name"] != current_user.full_name
    ):
        raise HTTPException(
            status_code=409, detail="Managed in EkLink: change your name in EkLink"
        )
    for field, value in changes.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user
