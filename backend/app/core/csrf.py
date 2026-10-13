"""
CSRF protection for cookie-authenticated requests.

Rule: an unsafe request (POST/PUT/PATCH/DELETE) must carry
`X-Requested-With: TemplateOS` when it

- carries a session cookie (`templateos_access` or `templateos_refresh`), or
- targets /auth/refresh or /auth/logout (cookie-only endpoints),

unless it carries an `Authorization: Bearer ...` header (browsers never
attach that cross-site without a CORS preflight, so it is not CSRF-able).
/auth/login and /auth/signup are exempt: there is no session to ride yet.

A cross-site form or `fetch(..., {mode: "no-cors"})` cannot set a custom
header, and a cross-origin `fetch` that sets one triggers a preflight that
CORS rejects for unlisted origins; SameSite=Lax cookies are the second layer.

Implemented as pure ASGI middleware so every router is covered without
touching the endpoint modules.
"""

import json

from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.security import (
    ACCESS_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    REFRESH_COOKIE_NAME,
)

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _auth_path(name: str) -> str:
    return f"{settings.api_v1_prefix}/auth/{name}"


class CSRFMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.exempt_paths = frozenset({_auth_path("login"), _auth_path("signup")})
        self.always_protected_paths = frozenset(
            {_auth_path("refresh"), _auth_path("logout")}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._allowed(scope):
            await self.app(scope, receive, send)
            return

        body = json.dumps({"detail": "Missing CSRF header"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _allowed(self, scope: Scope) -> bool:
        if scope["method"].upper() not in UNSAFE_METHODS:
            return True
        path = scope.get("path", "").rstrip("/") or "/"
        if path in self.exempt_paths:
            return True

        headers: dict[str, str] = {}
        cookie_header = ""
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
            if name == "cookie":
                cookie_header = f"{cookie_header}; {value}" if cookie_header else value
            else:
                headers[name] = value

        authorization = headers.get("authorization", "")
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return True

        if path not in self.always_protected_paths and not _has_session_cookie(
            cookie_header
        ):
            return True

        return headers.get(CSRF_HEADER_NAME.lower(), "") == CSRF_HEADER_VALUE


def _has_session_cookie(cookie_header: str) -> bool:
    # Same lenient parser Starlette uses for request.cookies, so whatever the
    # auth dependency would read as a session cookie is seen here too.
    if not cookie_header:
        return False
    cookies = cookie_parser(cookie_header)
    return ACCESS_COOKIE_NAME in cookies or REFRESH_COOKIE_NAME in cookies
