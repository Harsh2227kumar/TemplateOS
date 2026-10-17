"""
V1.6 Phase 2: PDF conversion status, Retry PDF and PDF download.

Coverage:
- GotenbergConverter with httpx.MockTransport: success (multipart "files",
  .docx name, connect/read timeouts), unreachable, timeout, HTTP status
  reasons, a body that is not a PDF, Gotenberg-Trace logging.
- generated_files CRUD: defaults, mark_pdf_converted, mark_pdf_failed
  (truncation, keeps an existing PDF), pdf_status validator.
- Endpoints (Gotenberg mocked, never a real service): generate converts,
  Gotenberg down still delivers the DOCX, disabled / not set up, retry
  success / failure (503) / idempotent / 404 / 403 / 410, download/pdf and
  ?format=pdf 404 / 409 / 410, regenerate resets the PDF state.
- Migration e3c9a7b5d1f2: backfill and up / down / up.
- One opt-in live test against a running Gotenberg (GOTENBERG_LIVE_URL).

Storage is redirected to a temporary folder; the database is in-memory
SQLite.
"""

import io
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests"
)

from app.core.config import Settings, settings
from app.crud.generated_file_crud import (
    mark_pdf_converted,
    mark_pdf_failed,
    upsert_generated_file,
)
from app.crud.template_field_crud import create_field
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.generated_file import PDF_STATUSES, GeneratedFile
from app.models.template import Template
from app.models.user import User
from app.schemas.template_field import TemplateFieldCreate
from app.services import pdf_service
from app.services.storage_service import storage_service

BACKEND_DIR = Path(__file__).resolve().parents[1]
FAKE_PDF = b"%PDF-1.7\n% fake pdf for tests\n%%EOF"
GOTENBERG_URL = "http://gotenberg.test:3000"
UNREACHABLE = (
    f"PDF service is not reachable at {GOTENBERG_URL}. Is Gotenberg running?"
)

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def override_get_db():
    with TestSession() as db:
        yield db


client = TestClient(app)

OWNER_EMAIL = "pdf_owner@example.com"
STRANGER_EMAIL = "pdf_stranger@example.com"


@pytest.fixture(scope="module", autouse=True)
def setup_db(tmp_path_factory):
    old = app.dependency_overrides.get(get_db)
    old_root = storage_service.root_path
    storage_service.root_path = tmp_path_factory.mktemp("pdf-storage").resolve()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    storage_service.root_path = old_root
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


class FakeGotenberg:
    """MockTransport handler: set .response or .error; .calls records requests."""

    def __init__(self) -> None:
        self.response = httpx.Response(200, content=FAKE_PDF)
        self.error: Exception | None = None
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture()
def gotenberg(monkeypatch) -> FakeGotenberg:
    """Gotenberg configured and mocked (never a real service, no soffice)."""
    fake = FakeGotenberg()
    monkeypatch.setattr(settings, "pdf_conversion_enabled", True)
    monkeypatch.setattr(settings, "pdf_converter", "auto")
    monkeypatch.setattr(settings, "gotenberg_url", GOTENBERG_URL)
    monkeypatch.setattr(settings, "gotenberg_timeout_seconds", 30)
    monkeypatch.setattr(settings, "libreoffice_path", None)
    monkeypatch.setattr(pdf_service, "gotenberg_transport", httpx.MockTransport(fake))
    return fake


def _docx_bytes(*paragraphs: str) -> bytes:
    document = DocxDocument()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login(email: str) -> str:
    client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Pdf Tester", "email": email, "password": "strong-password"},
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "strong-password"}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest.fixture(scope="module")
def owner_token(setup_db) -> str:
    return _signup_and_login(OWNER_EMAIL)


@pytest.fixture(scope="module")
def stranger_token(setup_db) -> str:
    return _signup_and_login(STRANGER_EMAIL)


@pytest.fixture()
def ready_doc(owner_token) -> int:
    """A saved draft whose template renders (title is the only field)."""
    stored = storage_service.save_bytes(
        "templates_processed", "pdf.docx", _docx_bytes("Title: {{ title }}")
    )
    with TestSession() as session:
        owner_id = session.execute(
            select(User.id).where(User.email == OWNER_EMAIL)
        ).scalar_one()
        template = Template(
            name="Pdf Template",
            category="mom",
            visibility="public",
            uploaded_by=owner_id,
            status="field_configured",
            processed_file_path=stored.path,
        )
        session.add(template)
        session.commit()
        create_field(
            session,
            template.id,
            TemplateFieldCreate(field_name="title", field_type="text", is_required=True),
        )
        template_id = template.id
    created = client.post(
        "/api/v1/documents/create",
        headers=_auth(owner_token),
        json={"template_id": template_id, "name": "Budget Minutes"},
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    saved = client.put(
        f"/api/v1/documents/{document_id}/values",
        headers=_auth(owner_token),
        json={"values": [{"field_name": "title", "value": "Budget review"}]},
    )
    assert saved.status_code == 200, saved.text
    return document_id


def _generate(token: str, document_id: int) -> httpx.Response:
    return client.post(f"/api/v1/documents/{document_id}/generate", headers=_auth(token))


def _retry(token: str, document_id: int) -> httpx.Response:
    return client.post(
        f"/api/v1/documents/{document_id}/generate-pdf", headers=_auth(token)
    )


def _download_pdf(token: str, document_id: int, query: bool = False) -> httpx.Response:
    base = f"/api/v1/documents/{document_id}/download"
    return client.get(f"{base}?format=pdf" if query else f"{base}/pdf", headers=_auth(token))


def _record(document_id: int) -> GeneratedFile:
    with TestSession() as session:
        return session.execute(
            select(GeneratedFile).where(GeneratedFile.document_id == document_id)
        ).scalar_one()


def _set_row(document_id: int, **values) -> None:
    with TestSession() as session:
        row = session.execute(
            select(GeneratedFile).where(GeneratedFile.document_id == document_id)
        ).scalar_one()
        for key, value in values.items():
            setattr(row, key, value)
        session.commit()


def _pdf_files() -> list[Path]:
    folder = storage_service.root_path / "generated" / "pdf"
    return sorted(folder.glob("*.pdf")) if folder.is_dir() else []


# ── 1. GotenbergConverter (MockTransport) ─────────────────────────


def _converter(handler) -> pdf_service.GotenbergConverter:
    return pdf_service.GotenbergConverter(
        GOTENBERG_URL + "/", 60, transport=httpx.MockTransport(handler)
    )


def test_gotenberg_converter_success_request_shape():
    fake = FakeGotenberg()
    assert _converter(fake).convert(b"PK fake docx", "minutes") == FAKE_PDF
    request = fake.calls[0]
    assert request.method == "POST"
    assert str(request.url) == f"{GOTENBERG_URL}/forms/libreoffice/convert"
    assert b'name="files"; filename="minutes.docx"' in request.content
    assert b"PK fake docx" in request.content
    assert request.extensions["timeout"]["connect"] == 5
    assert request.extensions["timeout"]["read"] == 60


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (400, "The document could not be converted (the PDF service rejected the file)"),
        (503, "PDF service is busy or timed out. Try again in a moment"),
        (500, "PDF service error (HTTP 500). Try again"),
        (418, "Unexpected PDF service response (HTTP 418)"),
    ],
)
def test_gotenberg_http_status_reasons(status_code, reason, caplog):
    def handler(_request):
        return httpx.Response(
            status_code, text="boom", headers={"Gotenberg-Trace": "trace-123"}
        )

    with caplog.at_level(logging.ERROR, logger="app.services.pdf_service"):
        with pytest.raises(pdf_service.PdfConversionError) as error:
            _converter(handler).convert(b"PK", "a.docx")
    assert str(error.value) == reason
    assert "trace=trace-123" in caplog.text


def test_gotenberg_unreachable_timeout_and_invalid_body():
    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(pdf_service.PdfConversionError) as error:
        _converter(refused).convert(b"PK", "a.docx")
    assert str(error.value) == UNREACHABLE

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(pdf_service.PdfConversionError) as error:
        _converter(slow).convert(b"PK", "a.docx")
    assert str(error.value) == "PDF conversion timed out after 60s"

    def html(_request):
        return httpx.Response(200, content=b"<html>not a pdf</html>")

    with pytest.raises(pdf_service.PdfConversionError) as error:
        _converter(html).convert(b"PK", "a.docx")
    assert str(error.value) == "PDF service returned an invalid file"


def test_gotenberg_url_setting_is_normalized():
    assert Settings.normalize_gotenberg_url(" http://localhost:3000/ ") == "http://localhost:3000"
    assert Settings.normalize_gotenberg_url("  ") is None
    assert Settings.normalize_gotenberg_url(None) is None


def test_unavailable_reasons(monkeypatch):
    monkeypatch.setattr(settings, "pdf_conversion_enabled", True)
    monkeypatch.setattr(settings, "pdf_converter", "auto")
    monkeypatch.setattr(settings, "gotenberg_url", None)
    monkeypatch.setattr(pdf_service, "find_libreoffice", lambda: None)
    assert pdf_service.get_pdf_converter() is None
    assert pdf_service.unavailable_reason() == (
        "PDF conversion is not set up on this server "
        "(set GOTENBERG_URL or install LibreOffice)"
    )

    monkeypatch.setattr(settings, "gotenberg_url", GOTENBERG_URL)
    monkeypatch.setattr(settings, "pdf_conversion_enabled", False)
    assert pdf_service.get_pdf_converter() is None
    assert pdf_service.unavailable_reason() == "PDF conversion is disabled on this server"
    assert pdf_service.check_pdf_setup()["converter"] is None

    monkeypatch.setattr(settings, "pdf_conversion_enabled", True)
    monkeypatch.setattr(settings, "pdf_converter", "none")
    assert pdf_service.unavailable_reason() == "PDF conversion is disabled on this server"


# ── 2. CRUD helpers ───────────────────────────────────────────────


def test_crud_pdf_state_helpers(ready_doc):
    with TestSession() as session:
        assert GeneratedFile(document_id=ready_doc, docx_path="generated/docx/a.docx").pdf_status == "pending"
        record, superseded = upsert_generated_file(
            session,
            ready_doc,
            docx_path="generated/docx/a.docx",
            generated_at=datetime(2026, 10, 15),
        )
        session.commit()
        assert superseded == []
        assert (record.pdf_status, record.pdf_attempts) == ("pending", 0)
        assert record.pdf_converted_at is None and record.has_pdf is False

        record = mark_pdf_converted(session, record, "generated/pdf/a.pdf")
        assert record.pdf_status == "converted"
        assert record.pdf_path == "generated/pdf/a.pdf"
        assert record.pdf_error is None
        assert record.pdf_attempts == 1
        assert record.pdf_converted_at is not None
        converted_at = record.pdf_converted_at

        record = mark_pdf_failed(session, record, "x" * 900)
        assert record.pdf_status == "failed"
        assert record.pdf_path == "generated/pdf/a.pdf"  # kept
        assert record.has_pdf is True
        assert len(record.pdf_error) == 500
        assert record.pdf_attempts == 2
        assert record.pdf_converted_at == converted_at

        # A new DOCX resets the PDF state and hands back the old files.
        record, superseded = upsert_generated_file(
            session,
            ready_doc,
            docx_path="generated/docx/b.docx",
            generated_at=converted_at,
        )
        session.commit()
        assert superseded == ["generated/docx/a.docx", "generated/pdf/a.pdf"]
        assert (record.pdf_status, record.pdf_attempts) == ("pending", 0)
        assert record.pdf_path is None and record.pdf_error is None
        assert record.pdf_converted_at is None


def test_pdf_status_validator():
    assert PDF_STATUSES == ("pending", "converted", "failed")
    record = GeneratedFile(document_id=1, docx_path="generated/docx/a.docx")
    with pytest.raises(ValueError):
        record.pdf_status = "done"
    with pytest.raises(ValueError):
        GeneratedFile(document_id=1, docx_path="x", pdf_status="ok")


# ── 3. POST /generate ─────────────────────────────────────────────


def test_generate_converts_and_pdf_downloads(owner_token, ready_doc, gotenberg):
    response = _generate(owner_token, ready_doc)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pdf_status"] == "converted"
    assert body["pdf_error"] is None
    assert body["has_pdf"] is True
    assert body["pdf_attempts"] == 1
    assert body["pdf_converted_at"]
    assert body["pdf_filename"].startswith("budget-minutes-")
    assert body["pdf_filename"].endswith(".pdf") and "/" not in body["pdf_filename"]
    assert body["pdf_url"] == f"/api/v1/documents/{ready_doc}/download/pdf"
    assert len(gotenberg.calls) == 1

    record = _record(ready_doc)
    assert record.pdf_path.startswith("generated/pdf/")
    assert storage_service.exists(record.pdf_path)

    for query in (False, True):
        download = _download_pdf(owner_token, ready_doc, query=query)
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/pdf"
        assert 'filename="Budget Minutes.pdf"' in download.headers["content-disposition"]
        assert download.content == FAKE_PDF

    detail = client.get(f"/api/v1/documents/{ready_doc}", headers=_auth(owner_token)).json()
    assert detail["generated"]["pdf_status"] == "converted"
    assert detail["generated"]["has_pdf"] is True
    listed = client.get("/api/v1/documents", headers=_auth(owner_token)).json()
    item = next(d for d in listed if d["id"] == ready_doc)["generated"]
    assert item["pdf_status"] == "converted"
    assert item["pdf_filename"] == body["pdf_filename"]
    assert item["pdf_attempts"] == 1


def test_gotenberg_down_still_delivers_docx(owner_token, ready_doc, gotenberg):
    gotenberg.error = httpx.ConnectError("refused")
    before = _pdf_files()
    response = _generate(owner_token, ready_doc)
    assert response.status_code == 200
    body = response.json()
    assert body["document_status"] == "generated"
    assert body["pdf_status"] == "failed"
    assert body["pdf_error"] == UNREACHABLE
    assert body["has_pdf"] is False
    assert body["pdf_url"] is None and body["pdf_filename"] is None
    assert body["pdf_attempts"] == 1
    assert _pdf_files() == before

    docx = client.get(
        f"/api/v1/documents/{ready_doc}/download?format=docx", headers=_auth(owner_token)
    )
    assert docx.status_code == 200
    assert docx.content.startswith(b"PK")
    for query in (False, True):
        assert _download_pdf(owner_token, ready_doc, query=query).status_code == 409


def test_generate_with_conversion_disabled(owner_token, ready_doc, gotenberg, monkeypatch):
    monkeypatch.setattr(settings, "pdf_conversion_enabled", False)
    body = _generate(owner_token, ready_doc).json()
    assert body["pdf_status"] == "failed"
    assert body["pdf_error"] == "PDF conversion is disabled on this server"
    assert gotenberg.calls == []


def test_generate_without_a_converter(owner_token, ready_doc, monkeypatch):
    monkeypatch.setattr(settings, "pdf_conversion_enabled", True)
    monkeypatch.setattr(settings, "pdf_converter", "auto")
    monkeypatch.setattr(settings, "gotenberg_url", None)
    monkeypatch.setattr(pdf_service, "find_libreoffice", lambda: None)
    response = _generate(owner_token, ready_doc)
    assert response.status_code == 200
    assert response.json()["pdf_status"] == "failed"
    assert response.json()["pdf_error"] == (
        "PDF conversion is not set up on this server "
        "(set GOTENBERG_URL or install LibreOffice)"
    )


def test_regenerate_resets_pdf_state_and_removes_old_files(owner_token, ready_doc, gotenberg):
    assert _generate(owner_token, ready_doc).json()["pdf_status"] == "converted"
    first = _record(ready_doc)

    gotenberg.error = httpx.ConnectError("refused")
    body = _generate(owner_token, ready_doc).json()
    assert body["pdf_status"] == "failed"
    assert body["pdf_attempts"] == 1  # counted for the new DOCX only
    assert body["has_pdf"] is False  # the old PDF belonged to the old DOCX
    second = _record(ready_doc)
    assert second.id == first.id
    assert second.pdf_path is None and second.pdf_converted_at is None
    assert not storage_service.exists(first.docx_path)
    assert not storage_service.exists(first.pdf_path)
    assert storage_service.exists(second.docx_path)


# ── 4. POST /generate-pdf (Retry PDF) ─────────────────────────────


def test_retry_success_after_failure(owner_token, ready_doc, gotenberg):
    gotenberg.error = httpx.ReadTimeout("slow")
    body = _generate(owner_token, ready_doc).json()
    assert body["pdf_status"] == "failed"
    assert body["pdf_error"] == "PDF conversion timed out after 30s"

    gotenberg.error = None
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 200, retry.text
    body = retry.json()
    assert body["pdf_status"] == "converted"
    assert body["pdf_error"] is None
    assert body["has_pdf"] is True
    assert body["pdf_attempts"] == 2
    assert body["document_id"] == ready_doc
    assert _download_pdf(owner_token, ready_doc).status_code == 200


def test_retry_failure_returns_503_and_keeps_existing_pdf(owner_token, ready_doc, gotenberg):
    assert _generate(owner_token, ready_doc).json()["pdf_status"] == "converted"
    existing = _record(ready_doc).pdf_path
    # An earlier retry failed: the row is "failed" but the PDF is still there.
    _set_row(ready_doc, pdf_status="failed", pdf_error="PDF service is busy")

    gotenberg.response = httpx.Response(503, text="busy")
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 503
    assert retry.json() == {"detail": "PDF service is busy or timed out. Try again in a moment"}

    record = _record(ready_doc)
    assert record.pdf_status == "failed"
    assert record.pdf_error == "PDF service is busy or timed out. Try again in a moment"
    assert record.pdf_attempts == 2
    assert record.pdf_path == existing and storage_service.exists(existing)

    detail = client.get(f"/api/v1/documents/{ready_doc}", headers=_auth(owner_token)).json()
    assert detail["generated"]["pdf_status"] == "failed"
    assert detail["generated"]["has_pdf"] is True
    assert _download_pdf(owner_token, ready_doc).status_code == 200

    # A later successful retry replaces (and removes) the earlier PDF.
    gotenberg.response = httpx.Response(200, content=FAKE_PDF)
    assert _retry(owner_token, ready_doc).json()["pdf_status"] == "converted"
    replaced = _record(ready_doc)
    assert replaced.pdf_path != existing
    assert not storage_service.exists(existing)
    assert replaced.pdf_attempts == 3


def test_retry_when_already_converted_is_idempotent(owner_token, ready_doc, gotenberg):
    assert _generate(owner_token, ready_doc).json()["pdf_status"] == "converted"
    calls = len(gotenberg.calls)
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 200
    assert retry.json()["pdf_status"] == "converted"
    assert retry.json()["pdf_attempts"] == 1
    assert len(gotenberg.calls) == calls


def test_retry_converts_a_pending_row(owner_token, ready_doc, gotenberg):
    assert _generate(owner_token, ready_doc).status_code == 200
    _set_row(ready_doc, pdf_status="pending", pdf_path=None, pdf_attempts=0)
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 200
    assert retry.json()["pdf_status"] == "converted"


def test_retry_disabled_is_503(owner_token, ready_doc, gotenberg, monkeypatch):
    assert _generate(owner_token, ready_doc).status_code == 200
    _set_row(ready_doc, pdf_status="failed")
    monkeypatch.setattr(settings, "pdf_conversion_enabled", False)
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 503
    assert retry.json()["detail"] == "PDF conversion is disabled on this server"


def test_retry_guards(owner_token, stranger_token, ready_doc, gotenberg):
    assert _retry(owner_token, ready_doc).status_code == 404  # never generated
    assert _retry(owner_token, 999_999).status_code == 404

    gotenberg.error = httpx.ConnectError("refused")
    assert _generate(owner_token, ready_doc).status_code == 200
    assert _retry(stranger_token, ready_doc).status_code == 403

    storage_service.delete_file(_record(ready_doc).docx_path)
    gotenberg.error = None
    retry = _retry(owner_token, ready_doc)
    assert retry.status_code == 410
    assert "missing" in retry.json()["detail"]
    assert len(gotenberg.calls) == 1  # only the failed generate; no new conversion


# ── 5. GET /download/pdf and ?format=pdf ──────────────────────────


def test_download_pdf_status_codes(owner_token, stranger_token, ready_doc, gotenberg):
    for query in (False, True):
        not_generated = _download_pdf(owner_token, ready_doc, query=query)
        assert not_generated.status_code == 404

    gotenberg.error = httpx.ConnectError("refused")
    assert _generate(owner_token, ready_doc).status_code == 200
    for query in (False, True):
        no_pdf = _download_pdf(owner_token, ready_doc, query=query)
        assert no_pdf.status_code == 409
        assert "Retry PDF" in no_pdf.json()["detail"]

    gotenberg.error = None
    assert _retry(owner_token, ready_doc).status_code == 200
    assert _download_pdf(stranger_token, ready_doc).status_code == 403
    storage_service.delete_file(_record(ready_doc).pdf_path)
    for query in (False, True):
        gone = _download_pdf(owner_token, ready_doc, query=query)
        assert gone.status_code == 410
        assert gone.json()["detail"] == "The PDF file is missing on the server. Use Retry PDF."

    # Retry repairs it: the row says converted but the file is gone.
    assert _retry(owner_token, ready_doc).json()["pdf_status"] == "converted"
    assert _download_pdf(owner_token, ready_doc).status_code == 200


# ── 6. Migration ──────────────────────────────────────────────────

PDF_REVISION = "e3c9a7b5d1f2"
PREVIOUS_REVISION = "d8f2a4c6e1b9"


def _alembic(environment: dict, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_pdf_status_migration_backfill_and_up_down_up(tmp_path: Path) -> None:
    db_file = tmp_path / "pdf.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    _alembic(environment, "upgrade", PREVIOUS_REVISION)
    with sqlite3.connect(db_file) as connection:
        connection.executemany(
            "INSERT INTO generated_files (id, document_id, docx_path, pdf_path, pdf_error) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, "generated/docx/a.docx", "generated/pdf/a.pdf", None),
                (2, 2, "generated/docx/b.docx", None, "PDF service timed out"),
                (3, 3, "generated/docx/c.docx", None, None),
            ],
        )

    def rows():
        with sqlite3.connect(db_file) as connection:
            return connection.execute(
                "SELECT id, pdf_status, pdf_error, pdf_attempts, pdf_converted_at "
                "FROM generated_files ORDER BY id"
            ).fetchall()

    _alembic(environment, "upgrade", PDF_REVISION)
    assert rows() == [
        (1, "converted", None, 0, None),
        (2, "failed", "PDF service timed out", 0, None),
        (3, "failed", "PDF conversion was not set up when this document was generated", 0, None),
    ]
    engine = create_engine(environment["DATABASE_URL"])
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("generated_files")}
    finally:
        engine.dispose()
    assert columns["pdf_status"]["nullable"] is False
    assert columns["pdf_attempts"]["nullable"] is False
    assert columns["pdf_converted_at"]["nullable"] is True
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "INSERT INTO generated_files (id, document_id, docx_path) "
            "VALUES (4, 4, 'generated/docx/d.docx')"
        )
        assert connection.execute(
            "SELECT pdf_status, pdf_attempts FROM generated_files WHERE id = 4"
        ).fetchone() == ("pending", 0)

    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("generated_files")}
    finally:
        engine.dispose()
    assert not {"pdf_status", "pdf_attempts", "pdf_converted_at"} & columns
    with sqlite3.connect(db_file) as connection:
        errors = connection.execute(
            "SELECT id, pdf_error FROM generated_files ORDER BY id"
        ).fetchall()
    assert errors == [(1, None), (2, "PDF service timed out"), (3, None), (4, None)]

    _alembic(environment, "upgrade", PDF_REVISION)
    assert [row[1] for row in rows()] == ["converted", "failed", "failed", "failed"]


# ── 7. Live Gotenberg (opt-in) ────────────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("GOTENBERG_LIVE_URL"),
    reason="set GOTENBERG_LIVE_URL (e.g. http://localhost:3000) to run against a real Gotenberg",
)
def test_live_gotenberg_conversion():
    converter = pdf_service.GotenbergConverter(os.environ["GOTENBERG_LIVE_URL"], 60)
    pdf = converter.convert(_docx_bytes("TemplateOS live Gotenberg check"), "live-check.docx")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
