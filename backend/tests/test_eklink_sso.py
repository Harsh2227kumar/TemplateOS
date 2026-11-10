"""
EkLink single sign-on: config endpoint, state cookie + redirect, callback
(state check, code exchange, JWT verification, user matching/creation,
session cookies). EkLink itself is faked: httpx.post and the JWKS client.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Department, Organization
from app.models.user import User
from app.services import eklink

PREFIX = settings.api_v1_prefix
CSRF = {"X-Requested-With": "TemplateOS"}
EKLINK_URL = "http://eklink.test"
CLIENT_ID = "templateos_test"

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


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


@pytest.fixture(autouse=True)
def eklink_settings(monkeypatch):
    monkeypatch.setattr(settings, "eklink_url", EKLINK_URL)
    monkeypatch.setattr(settings, "eklink_issuer_setting", None)
    monkeypatch.setattr(settings, "eklink_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "eklink_client_secret", "client-secret")
    monkeypatch.setattr(
        settings, "eklink_redirect_uri", "http://localhost:5173/auth/callback"
    )
    monkeypatch.setattr(settings, "eklink_organization", None)
    monkeypatch.setattr(
        eklink,
        "_jwks",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                key=SIGNING_KEY.public_key()
            )
        ),
    )


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _token(key=SIGNING_KEY, **overrides) -> str:
    claims = {
        "sub": "eklink-user-1",
        "email": "Asha@College.edu",
        "name": "Asha Rao",
        "role": "faculty",
        "department": "CSE",
        "iss": EKLINK_URL,
        "aud": CLIENT_ID,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="ES256")


def _fake_token_endpoint(monkeypatch, token: str | None = None, status_code: int = 200):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        body = {"access_token": token or _token(), "token_type": "Bearer"}
        return httpx.Response(status_code, json=body if status_code == 200 else {"error": "x"})

    monkeypatch.setattr(eklink.httpx, "post", fake_post)
    return calls


def _start_login(client: TestClient) -> str:
    response = client.get(f"{PREFIX}/auth/eklink/login", follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_config_reports_disabled_without_settings(client, monkeypatch):
    monkeypatch.setattr(settings, "eklink_client_secret", None)
    assert client.get(f"{PREFIX}/auth/eklink").json() == {
        "enabled": False,
        "eklink_url": None,
        "signup_enabled": True,  # tests turn public sign-up on (conftest.py)
    }
    assert client.get(f"{PREFIX}/auth/eklink/login", follow_redirects=False).status_code == 404


def test_config_reports_enabled(client):
    assert client.get(f"{PREFIX}/auth/eklink").json() == {
        "enabled": True,
        "eklink_url": EKLINK_URL,
        "signup_enabled": True,
    }


def test_login_redirects_to_eklink_with_state_cookie(client):
    response = client.get(f"{PREFIX}/auth/eklink/login", follow_redirects=False)
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{EKLINK_URL}/authorize"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["http://localhost:5173/auth/callback"]
    assert response.cookies.get(eklink.STATE_COOKIE_NAME) == query["state"][0]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_callback_creates_user_and_sets_session(client, monkeypatch):
    calls = _fake_token_endpoint(monkeypatch)
    state = _start_login(client)

    response = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": state}, headers=CSRF
    )

    assert response.status_code == 200, response.text
    assert calls[0][0] == f"{EKLINK_URL}/token"
    assert calls[0][1]["client_secret"] == "client-secret"
    assert calls[0][1]["code"] == "abc"
    assert response.cookies.get(ACCESS_COOKIE_NAME)
    assert response.cookies.get(REFRESH_COOKIE_NAME)
    me = client.get(f"{PREFIX}/auth/me").json()
    assert me["email"] == "asha@college.edu"
    assert me["full_name"] == "Asha Rao"
    assert me["role"] == "faculty"


def test_callback_reuses_existing_user_and_keeps_role(client, monkeypatch):
    with TestSession() as db:
        db.add(User(email="asha@college.edu", full_name="Asha", role="department_admin"))
        db.commit()
    _fake_token_endpoint(monkeypatch, _token(role="student"))
    state = _start_login(client)

    response = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": state}, headers=CSRF
    )

    assert response.status_code == 200
    assert client.get(f"{PREFIX}/auth/me").json()["role"] == "department_admin"
    with TestSession() as db:
        assert len(db.scalars(select(User)).all()) == 1


def test_new_user_joins_configured_organization_and_department(client, monkeypatch):
    with TestSession() as db:
        organization = Organization(name="SIT")
        db.add(organization)
        db.flush()
        db.add(Department(organization_id=organization.id, name="cse"))
        db.commit()
    monkeypatch.setattr(settings, "eklink_organization", "SIT")
    _fake_token_endpoint(monkeypatch)
    state = _start_login(client)

    client.post(f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": state}, headers=CSRF)

    with TestSession() as db:
        user = db.scalar(select(User))
        assert user.organization == "SIT"
        assert user.department == "cse"


def test_callback_rejects_missing_or_wrong_state(client, monkeypatch):
    calls = _fake_token_endpoint(monkeypatch)
    no_cookie = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": "x"}, headers=CSRF
    )
    _start_login(client)
    wrong = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": "x"}, headers=CSRF
    )
    assert no_cookie.status_code == 400
    assert wrong.status_code == 400
    assert calls == []


@pytest.mark.parametrize(
    "token",
    [
        _token(key=OTHER_KEY),
        _token(aud="another-app"),
        _token(iss="http://evil.test"),
        _token(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
    ],
    ids=["bad-signature", "wrong-audience", "wrong-issuer", "expired"],
)
def test_callback_rejects_invalid_tokens(client, monkeypatch, token):
    _fake_token_endpoint(monkeypatch, token)
    state = _start_login(client)
    response = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": state}, headers=CSRF
    )
    assert response.status_code == 401
    assert ACCESS_COOKIE_NAME not in response.cookies
    with TestSession() as db:
        assert db.scalar(select(User)) is None


def test_callback_reports_rejected_code(client, monkeypatch):
    _fake_token_endpoint(monkeypatch, status_code=400)
    state = _start_login(client)
    response = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "used", "state": state}, headers=CSRF
    )
    assert response.status_code == 401


def test_callback_rejects_role_without_access(client, monkeypatch):
    _fake_token_endpoint(monkeypatch, _token(role="visitor"))
    state = _start_login(client)
    response = client.post(
        f"{PREFIX}/auth/eklink/callback", json={"code": "abc", "state": state}, headers=CSRF
    )
    assert response.status_code == 403
