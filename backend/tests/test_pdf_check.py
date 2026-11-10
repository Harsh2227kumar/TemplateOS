"""GET /system/pdf-check: which PDF converter is configured and whether it answers."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import pdf_service

client = TestClient(app)
URL = "/api/v1/system/pdf-check"


@pytest.fixture()
def gotenberg(monkeypatch):
    monkeypatch.setattr(settings, "pdf_converter", "auto")
    monkeypatch.setattr(settings, "gotenberg_url", "http://gotenberg.test:3000/")


def test_not_configured_explains_the_fix(monkeypatch):
    monkeypatch.setattr(settings, "pdf_converter", "auto")
    monkeypatch.setattr(settings, "gotenberg_url", None)
    monkeypatch.setattr(pdf_service, "find_libreoffice", lambda: None)

    body = client.get(URL).json()

    assert body["converter"] is None
    assert body["ok"] is False
    assert "GOTENBERG_URL" in body["message"]


def test_gotenberg_healthy(gotenberg, monkeypatch):
    seen = []

    def fake_get(url, timeout):
        seen.append(url)
        return httpx.Response(200, json={"status": "up"})

    monkeypatch.setattr(pdf_service.httpx, "get", fake_get)

    body = client.get(URL).json()

    assert body == {"converter": "gotenberg", "ok": True, "message": "Gotenberg is reachable"}
    assert seen == ["http://gotenberg.test:3000/health"]


def test_gotenberg_unreachable(gotenberg, monkeypatch):
    def fake_get(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(pdf_service.httpx, "get", fake_get)

    body = client.get(URL).json()

    assert body["converter"] == "gotenberg"
    assert body["ok"] is False
    assert "not reachable" in body["message"]


def test_gotenberg_unhealthy(gotenberg, monkeypatch):
    monkeypatch.setattr(pdf_service.httpx, "get", lambda url, timeout: httpx.Response(503))

    body = client.get(URL).json()

    assert body["ok"] is False
    assert "HTTP 503" in body["message"]


def test_converter_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "pdf_converter", "none")
    assert client.get(URL).json()["converter"] is None
