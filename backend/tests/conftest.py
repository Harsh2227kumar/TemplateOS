import os

import pytest

# Most suites create their users through POST /auth/signup. Public sign-up is
# off by default in the app (accounts come from EkLink or an admin), so turn
# it on for the test process before any test module imports the app.
os.environ.setdefault("ALLOW_PUBLIC_SIGNUP", "true")
# EkLink sync makes people / directory / approvers read-only. Off for the
# suites (the developer's .env may configure EkLink); tests/test_eklink_sync.py
# switches it on where it is needed.
os.environ.setdefault("EKLINK_SYNC_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter():
    # The login limiter is process-global and every test module's TestClient
    # shares one client IP, so start each test with a clean slate. Imported
    # lazily: test modules set DATABASE_URL/JWT_SECRET_KEY before app import.
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    """
    /auth/login sets httpOnly session cookies, and the module-level
    TestClient instances keep a cookie jar. The pre-existing suites log in
    (often inside fixtures) and then authenticate with Bearer headers, and
    their "requires auth" checks expect an anonymous request. Clear the jar
    of every module-level TestClient after fixture setup, right before the
    test body runs. Cookie-session behaviour is covered by
    tests/test_cookie_auth.py, which uses its own per-test clients.
    """
    from fastapi.testclient import TestClient

    module = getattr(item, "module", None)
    if module is None:
        return
    for value in vars(module).values():
        if isinstance(value, TestClient):
            value.cookies.clear()
