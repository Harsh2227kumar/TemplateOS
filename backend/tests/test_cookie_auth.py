"""
Cookie sessions: httpOnly access/refresh cookies, refresh-token rotation with
reuse detection, logout, CSRF header rule, credentialed CORS, login rate
limiting and the refresh_tokens migration.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter, login_rate_limiter
from app.core.security import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.crud.refresh_token_crud import hash_refresh_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.refresh_token import RefreshToken

BACKEND_DIR = Path(__file__).resolve().parents[1]
PREFIX = settings.api_v1_prefix
CSRF = {"X-Requested-With": "TemplateOS"}
PASSWORD = "strong-password"

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_get_db():
    with TestSession() as db:
        yield db


@pytest.fixture(autouse=True)
def database():
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    # A fresh client (and cookie jar) per test.
    with TestClient(app) as test_client:
        yield test_client


def _signup(client: TestClient, email: str = "cookie@example.com") -> None:
    response = client.post(
        f"{PREFIX}/auth/signup",
        json={"full_name": "Cookie User", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text


def _login(client: TestClient, email: str = "cookie@example.com"):
    response = client.post(
        f"{PREFIX}/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response


def _set_cookie_headers(response) -> dict[str, str]:
    headers = {}
    for raw in response.headers.get_list("set-cookie"):
        headers[raw.split("=", 1)[0]] = raw
    return headers


def _attributes(raw_cookie: str) -> dict[str, str]:
    attributes = {}
    for part in raw_cookie.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        attributes[name.lower()] = value
    return attributes


def _put_cookie(client: TestClient, name: str, value: str) -> None:
    """Replace a cookie the way a browser jar would hold it (one per name)."""
    for cookie in list(client.cookies.jar):
        if cookie.name == name:
            client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    path = f"{PREFIX}/auth" if name == REFRESH_COOKIE_NAME else "/"
    client.cookies.set(name, value, domain="testserver.local", path=path)


def _not_csrf_blocked(response) -> bool:
    if response.status_code != 403:
        return True
    return response.json().get("detail") != "Missing CSRF header"


def _refresh_cookie(client: TestClient) -> str | None:
    return client.cookies.get(REFRESH_COOKIE_NAME)


def _rows() -> list[RefreshToken]:
    with TestSession() as db:
        return list(db.scalars(select(RefreshToken).order_by(RefreshToken.id)))


def _assert_cleared(response) -> None:
    cookies = _set_cookie_headers(response)
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        assert name in cookies
        assert _attributes(cookies[name]).get("max-age") == "0"


# --- login ---------------------------------------------------------------


def test_login_sets_httponly_cookies_and_returns_token(client):
    _signup(client)
    response = _login(client)

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    cookies = _set_cookie_headers(response)
    access = _attributes(cookies[ACCESS_COOKIE_NAME])
    refresh = _attributes(cookies[REFRESH_COOKIE_NAME])

    assert cookies[ACCESS_COOKIE_NAME].startswith(
        f"{ACCESS_COOKIE_NAME}={body['access_token']};"
    )
    assert "httponly" in access and "httponly" in refresh
    assert access["path"] == "/"
    assert refresh["path"] == f"{PREFIX}/auth"
    assert access["samesite"].lower() == "lax"
    assert refresh["samesite"].lower() == "lax"
    assert access["max-age"] == str(settings.access_token_expire_minutes * 60)
    assert refresh["max-age"] == str(settings.refresh_token_expire_days * 86400)
    # Development defaults: not Secure, host-only.
    assert "secure" not in access and "secure" not in refresh
    assert "domain" not in access and "domain" not in refresh

    # Stored hashed, never raw.
    rows = _rows()
    assert len(rows) == 1
    raw_refresh = _refresh_cookie(client)
    assert rows[0].token_hash == hash_refresh_token(raw_refresh)
    assert rows[0].token_hash != raw_refresh
    assert rows[0].revoked_at is None


def test_cookie_secure_and_domain_settings(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure_override", True)
    monkeypatch.setattr(settings, "cookie_domain_setting", "example.test")
    _signup(client)
    response = _login(client)
    for raw in _set_cookie_headers(response).values():
        attributes = _attributes(raw)
        assert "secure" in attributes
        assert attributes["domain"] == "example.test"


def test_settings_defaults():
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 7
    assert settings.cookie_secure is False  # APP_ENV is not production in tests
    assert settings.cookie_domain is None


def test_login_cleans_up_expired_refresh_tokens(client):
    _signup(client)
    _login(client)
    with TestSession() as db:
        db.execute(
            update(RefreshToken).values(
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(minutes=1)
            )
        )
        db.commit()
    _login(client)
    rows = _rows()
    assert len(rows) == 1
    assert rows[0].token_hash == hash_refresh_token(_refresh_cookie(client))


# --- /me -----------------------------------------------------------------


def test_me_with_cookie_with_bearer_and_with_neither(client):
    _signup(client)
    token = _login(client).json()["access_token"]

    with_cookie = client.get(f"{PREFIX}/auth/me")
    assert with_cookie.status_code == 200
    assert with_cookie.json()["email"] == "cookie@example.com"

    anonymous = TestClient(app)
    with_bearer = anonymous.get(
        f"{PREFIX}/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert with_bearer.status_code == 200
    assert with_bearer.json() == with_cookie.json()

    assert anonymous.get(f"{PREFIX}/auth/me").status_code == 401


def test_invalid_bearer_does_not_fall_back_to_cookie(client):
    _signup(client)
    _login(client)
    response = client.get(
        f"{PREFIX}/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


def test_invalid_access_cookie_is_rejected(client):
    _signup(client)
    _login(client)
    _put_cookie(client, ACCESS_COOKIE_NAME, "garbage")
    assert client.get(f"{PREFIX}/auth/me").status_code == 401


# --- refresh -------------------------------------------------------------


def test_refresh_rotates_tokens(client):
    _signup(client)
    _login(client)
    first_refresh = _refresh_cookie(client)

    response = client.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "bearer"
    cookies = _set_cookie_headers(response)
    assert ACCESS_COOKIE_NAME in cookies and REFRESH_COOKIE_NAME in cookies

    second_refresh = _refresh_cookie(client)
    assert second_refresh and second_refresh != first_refresh

    old, new = _rows()
    assert old.token_hash == hash_refresh_token(first_refresh)
    assert old.revoked_at is not None
    assert old.replaced_by_id == new.id
    assert new.token_hash == hash_refresh_token(second_refresh)
    assert new.revoked_at is None
    assert new.family_id == old.family_id

    assert client.get(f"{PREFIX}/auth/me").status_code == 200


def test_reusing_rotated_refresh_token_revokes_family(client):
    _signup(client)
    _login(client)
    stolen = _refresh_cookie(client)
    assert client.post(f"{PREFIX}/auth/refresh", headers=CSRF).status_code == 200
    current = _refresh_cookie(client)

    attacker = TestClient(app)
    _put_cookie(attacker, REFRESH_COOKIE_NAME, stolen)
    reuse = attacker.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert reuse.status_code == 401
    _assert_cleared(reuse)

    # Every token in the family is now revoked, including the legitimate one.
    assert all(row.revoked_at is not None for row in _rows())
    _put_cookie(client, REFRESH_COOKIE_NAME, current)
    assert client.post(f"{PREFIX}/auth/refresh", headers=CSRF).status_code == 401


def test_reuse_only_revokes_that_family(client):
    _signup(client)
    _login(client)
    stolen = _refresh_cookie(client)
    client.post(f"{PREFIX}/auth/refresh", headers=CSRF)

    other_device = TestClient(app)
    _login(other_device)

    attacker = TestClient(app)
    _put_cookie(attacker, REFRESH_COOKIE_NAME, stolen)
    assert attacker.post(f"{PREFIX}/auth/refresh", headers=CSRF).status_code == 401

    assert other_device.post(f"{PREFIX}/auth/refresh", headers=CSRF).status_code == 200


def test_refresh_missing_or_invalid_token_is_401_and_clears_cookies(client):
    missing = client.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert missing.status_code == 401
    _assert_cleared(missing)

    _put_cookie(client, REFRESH_COOKIE_NAME, "not-a-real-token")
    invalid = client.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert invalid.status_code == 401
    _assert_cleared(invalid)


def test_refresh_with_expired_refresh_token_is_401(client):
    _signup(client)
    _login(client)
    with TestSession() as db:
        db.execute(
            update(RefreshToken).values(
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(seconds=1)
            )
        )
        db.commit()
    response = client.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert response.status_code == 401
    _assert_cleared(response)


def test_refresh_requires_csrf_header(client):
    _signup(client)
    _login(client)
    response = client.post(f"{PREFIX}/auth/refresh")
    assert response.status_code == 403
    assert response.json() == {"detail": "Missing CSRF header"}
    # Nothing was rotated.
    assert len(_rows()) == 1 and _rows()[0].revoked_at is None


def test_expired_access_token_then_refresh(client):
    _signup(client)
    _login(client)
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    _put_cookie(client, ACCESS_COOKIE_NAME, expired)
    assert client.get(f"{PREFIX}/auth/me").status_code == 401

    refreshed = client.post(f"{PREFIX}/auth/refresh", headers=CSRF)
    assert refreshed.status_code == 200
    assert client.cookies.get(ACCESS_COOKIE_NAME) != expired
    assert client.get(f"{PREFIX}/auth/me").status_code == 200


# --- logout --------------------------------------------------------------


def test_logout_revokes_and_clears_cookies(client):
    _signup(client)
    _login(client)
    refresh = _refresh_cookie(client)

    response = client.post(f"{PREFIX}/auth/logout", headers=CSRF)
    assert response.status_code == 204
    _assert_cleared(response)
    assert client.cookies.get(ACCESS_COOKIE_NAME) is None
    assert _refresh_cookie(client) is None
    assert all(row.revoked_at is not None for row in _rows())

    _put_cookie(client, REFRESH_COOKIE_NAME, refresh)
    assert client.post(f"{PREFIX}/auth/refresh", headers=CSRF).status_code == 401


def test_logout_works_with_expired_access_token(client):
    _signup(client)
    _login(client)
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    _put_cookie(client, ACCESS_COOKIE_NAME, expired)
    assert client.post(f"{PREFIX}/auth/logout", headers=CSRF).status_code == 204
    assert _rows()[0].revoked_at is not None


def test_logout_without_session_is_204(client):
    response = client.post(f"{PREFIX}/auth/logout", headers=CSRF)
    assert response.status_code == 204
    _assert_cleared(response)


def test_logout_requires_csrf_header(client):
    _signup(client)
    _login(client)
    assert client.post(f"{PREFIX}/auth/logout").status_code == 403
    assert _rows()[0].revoked_at is None


# --- CSRF ----------------------------------------------------------------


def test_csrf_header_required_for_cookie_authenticated_unsafe_requests(client):
    _signup(client)
    token = _login(client).json()["access_token"]
    url = f"{PREFIX}/templates/999999"

    blocked = client.delete(url)
    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "Missing CSRF header"}

    wrong_value = client.delete(url, headers={"X-Requested-With": "XMLHttpRequest"})
    assert wrong_value.status_code == 403

    # With the header the request reaches the endpoint.
    assert _not_csrf_blocked(client.delete(url, headers=CSRF))

    # Safe methods never need it.
    assert client.get(f"{PREFIX}/auth/me").status_code == 200

    # Bearer-authenticated requests are exempt, even with cookies present.
    bearer = {"Authorization": f"Bearer {token}"}
    assert _not_csrf_blocked(client.delete(url, headers=bearer))
    anonymous = TestClient(app)
    assert _not_csrf_blocked(anonymous.delete(url, headers=bearer))


def test_login_and_signup_are_csrf_exempt(client):
    _signup(client)
    _login(client)  # cookies now present, no CSRF header sent
    _signup(client, "second@example.com")
    _login(client, "second@example.com")


def test_unsafe_request_without_any_credentials_is_not_csrf_blocked():
    anonymous = TestClient(app)
    assert anonymous.delete(f"{PREFIX}/templates/999999").status_code == 401


# --- CORS ----------------------------------------------------------------


def test_cors_allows_credentials_for_configured_origin():
    origin = settings.cors_origins[0]
    anonymous = TestClient(app)
    preflight = anonymous.options(
        f"{PREFIX}/auth/refresh",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-requested-with",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert preflight.headers["access-control-allow-credentials"] == "true"
    allowed_headers = preflight.headers["access-control-allow-headers"].lower()
    for header in ("content-type", "authorization", "x-requested-with"):
        assert header in allowed_headers

    simple = anonymous.get("/health", headers={"Origin": origin})
    assert simple.headers["access-control-allow-origin"] == origin
    assert simple.headers["access-control-allow-credentials"] == "true"

    foreign = anonymous.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in foreign.headers


def test_csrf_rejection_carries_cors_headers(client):
    _signup(client)
    _login(client)
    origin = settings.cors_origins[0]
    response = client.post(f"{PREFIX}/auth/logout", headers={"Origin": origin})
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == origin


# --- rate limiting -------------------------------------------------------


def test_login_rate_limit_returns_429_with_retry_after(client):
    _signup(client)
    limit = settings.login_rate_limit_attempts
    for _ in range(limit):
        response = client.post(
            f"{PREFIX}/auth/login",
            json={"email": "cookie@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        f"{PREFIX}/auth/login",
        json={"email": "cookie@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429
    retry_after = int(blocked.headers["retry-after"])
    assert 0 < retry_after <= settings.login_rate_limit_window_seconds

    login_rate_limiter.reset()
    assert client.post(
        f"{PREFIX}/auth/login",
        json={"email": "cookie@example.com", "password": PASSWORD},
    ).status_code == 200


def test_login_rate_limit_is_per_email_too(client, monkeypatch):
    monkeypatch.setattr(
        login_rate_limiter, "backend", InMemoryRateLimiter(limit=2, window_seconds=60)
    )
    for _ in range(2):
        client.post(
            f"{PREFIX}/auth/login",
            json={"email": "victim@example.com", "password": "wrong-password"},
        )
    # The email bucket is full: blocked even from a fresh IP...
    assert not login_rate_limiter.check("203.0.113.9", "Victim@Example.com").allowed
    # ...while another email from another fresh IP is fine.
    assert login_rate_limiter.check("203.0.113.10", "other@example.com").allowed
    # And the IP bucket is full for the test client's IP, whatever the email.
    blocked = client.post(
        f"{PREFIX}/auth/login",
        json={"email": "someone-else@example.com", "password": "wrong-password"},
    )
    assert blocked.status_code == 429


def test_in_memory_rate_limiter_window_slides():
    now = [1000.0]
    limiter = InMemoryRateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.hit("k").allowed
    now[0] += 4
    assert limiter.hit("k").allowed
    blocked = limiter.hit("k")
    assert not blocked.allowed and blocked.retry_after == 6
    now[0] += 6
    assert limiter.hit("k").allowed
    assert limiter.hit("other").allowed
    limiter.reset()
    assert limiter.hit("k").allowed and limiter.hit("k").allowed


# --- migration -----------------------------------------------------------


def _alembic(environment: dict, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_refresh_tokens_migration_up_down_up(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'refresh.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }

    def tables() -> set[str]:
        engine = create_engine(environment["DATABASE_URL"])
        try:
            return set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    _alembic(environment, "upgrade", "a3c7e1f9b2d6")
    assert "refresh_tokens" not in tables()

    _alembic(environment, "upgrade", "head")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("refresh_tokens")}
        assert set(columns) == {
            "id",
            "user_id",
            "token_hash",
            "family_id",
            "created_at",
            "expires_at",
            "revoked_at",
            "replaced_by_id",
        }
        assert columns["revoked_at"]["nullable"] is True
        assert columns["replaced_by_id"]["nullable"] is True
        assert columns["token_hash"]["nullable"] is False
        indexed = {
            tuple(index["column_names"]) for index in inspector.get_indexes("refresh_tokens")
        }
        assert ("user_id",) in indexed and ("family_id",) in indexed
        unique = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("refresh_tokens")
        }
        assert ("token_hash",) in unique
        foreign = {
            fk["referred_table"]: fk for fk in inspector.get_foreign_keys("refresh_tokens")
        }
        assert foreign["users"]["options"].get("ondelete") == "CASCADE"
    finally:
        engine.dispose()

    _alembic(environment, "downgrade", "a3c7e1f9b2d6")
    assert "refresh_tokens" not in tables()

    _alembic(environment, "upgrade", "head")
    assert "refresh_tokens" in tables()
