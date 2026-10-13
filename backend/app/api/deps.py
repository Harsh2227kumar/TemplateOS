from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import ACCESS_COOKIE_NAME, decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> User:
    """
    Resolve the user from `Authorization: Bearer <jwt>` (scripts, tests) or,
    when that header is absent, from the httpOnly `templateos_access` cookie
    (browser sessions). A bad Bearer token is rejected outright; it never
    falls back to the cookie. CSRF for cookie requests is enforced by
    app.core.csrf.CSRFMiddleware.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is not None:
        if credentials.scheme.lower() != "bearer":
            raise credentials_error
        token = credentials.credentials
    elif request.headers.get("authorization"):
        # Present but not a usable Bearer header (e.g. "Basic ...").
        raise credentials_error
    else:
        token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise credentials_error

    try:
        user_id = int(decode_access_token(token))
    except (jwt.InvalidTokenError, ValueError):
        raise credentials_error from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
