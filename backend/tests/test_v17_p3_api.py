"""
V1.7 Phase 3 API (Member 2): download history + audit hooks + history/audit endpoints.

Coverage:
- Downloads: latest DOCX, latest PDF and a version's PDF each record one
  history row and one document.download audit row (name, size, version);
  403 / 404 / 409 record nothing; a manual-edit version records
  version_source "manual_edit"; the Document Server's file fetch records nothing.
- /me/downloads (own rows only, filters) and /documents/{id}/downloads (owner only).
- Hooks: upload, fields sync, values save (names only: a sentinel value never
  reaches details), generate (+ replaced_manual_edits), AI improve-text,
  admin user update, login / failed login / logout, P2.1 customize,
  session open (not when reused), document file edit, save failure.
- An audit write failure never fails the action.
- Audit scoping (super / org / department admin, faculty 403), filters,
  date validation (422), CSV export (scoped, formula-safe, audited).

Storage is a temporary folder; the database is in-memory SQLite with
foreign keys on; PDF conversion and the Document Server are fakes.
"""

import csv
import io
import json
import os
from urllib.parse import urlsplit

import httpx
import jwt
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.core.config import settings  # noqa: E402
from app.crud import audit_log_crud  # noqa: E402
from app.crud.template_field_crud import create_field  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.download_history import DownloadHistory  # noqa: E402
from app.models.organization import Department, Organization  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.template_field import TemplateFieldCreate  # noqa: E402
from app.services import ai_service, audit_service, document_generation, onlyoffice_service  # noqa: E402
from app.services.storage_service import storage_service  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    with TestSession() as db:
        yield db


client = TestClient(app)
API = "/api/v1"
SECRET = "onlyoffice-test-secret-that-is-long-enough-0123"
DOCS = "http://docs.test:8082"
FAKE_PDF = b"%PDF-1.4\n% fake\n" + b"0" * 400
SENTINEL = "SECRET-VALUE-7731"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(scope="module", autouse=True)
def setup_db(tmp_path_factory):
    old = app.dependency_overrides.get(get_db)
    old_root = storage_service.root_path
    storage_service.root_path = tmp_path_factory.mktemp("p3-storage").resolve()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    storage_service.root_path = old_root
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


class FakeConverter:
    def convert(self, docx_bytes: bytes, filename: str) -> bytes:
        return FAKE_PDF


class FakeDocumentServer:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def publish(self, content: bytes, name: str = "edited.docx") -> str:
        self.files[name] = content
        return f"{DOCS}/cache/files/{name}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=self.files[name]) if name in self.files else httpx.Response(404)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    server = FakeDocumentServer()
    monkeypatch.setattr(document_generation, "get_pdf_converter", lambda: FakeConverter())
    monkeypatch.setattr(settings, "generated_versions_keep_files", 10)
    monkeypatch.setattr(settings, "onlyoffice_enabled", True)
    monkeypatch.setattr(settings, "onlyoffice_public_url", DOCS)
    monkeypatch.setattr(settings, "onlyoffice_internal_url", None)
    monkeypatch.setattr(settings, "onlyoffice_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "backend_url_for_onlyoffice", "http://backend.test")
    monkeypatch.setattr(onlyoffice_service, "document_server_transport", httpx.MockTransport(server.handler))
    return server


def docx(*paragraphs: str) -> bytes:
    document = DocxDocument()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


_n = {"value": 0}


def _login(role: str = "faculty", organization_id: int | None = None, department_id: int | None = None):
    _n["value"] += 1
    email = f"p3_{_n['value']}@example.com"
    client.post(f"{API}/auth/signup", json={"full_name": f"User {_n['value']}", "email": email,
                                            "password": "strong-password"})
    with TestSession() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        user.role = role
        user.organization_id = organization_id
        user.department_id = department_id
        db.commit()
        user_id = user.id
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "strong-password"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"], user_id, email


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _org_and_dept() -> tuple[int, int]:
    with TestSession() as db:
        org = Organization(name=f"Org {_n['value']}-{os.urandom(3).hex()}")
        db.add(org)
        db.flush()
        dept = Department(organization_id=org.id, name="CSE")
        db.add(dept)
        db.commit()
        return org.id, dept.id


def _template(owner_id: int, org_id: int | None = None, dept_id: int | None = None) -> int:
    content = docx("Title: {{ title }}")
    path = storage_service.save_bytes("templates_processed", "mom.docx", content).path
    with TestSession() as db:
        template = Template(
            name="MoM", category="mom", visibility="public", status="active", uploaded_by=owner_id,
            original_file_path=path, processed_file_path=path, original_filename="mom.docx",
            scope_organization_id=org_id, scope_department_id=dept_id,
        )
        db.add(template)
        db.commit()
        create_field(db, template.id, TemplateFieldCreate(field_name="title", field_type="text",
                                                          is_required=True, ai_enabled=True))
        return template.id


def _generated_document(token: str, template_id: int) -> int:
    document = client.post(f"{API}/documents/create", json={"template_id": template_id, "name": "Budget"},
                           headers=_auth(token)).json()
    saved = client.put(f"{API}/documents/{document['id']}/values",
                       json={"values": [{"field_name": "title", "value": SENTINEL}]}, headers=_auth(token))
    assert saved.status_code == 200, saved.text
    generated = client.post(f"{API}/documents/{document['id']}/generate", headers=_auth(token))
    assert generated.status_code == 200, generated.text
    return document["id"]


def _count(model, *conditions) -> int:
    with TestSession() as db:
        return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def _audit(action: str, entity_id: int | None = None) -> list[AuditLog]:
    with TestSession() as db:
        statement = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        if entity_id is not None:
            statement = statement.where(AuditLog.entity_id == entity_id)
        return list(db.scalars(statement))


# ── Downloads ────────────────────────────────────────────────────


def test_each_download_route_records_once_and_failures_record_nothing():
    org_id, dept_id = _org_and_dept()
    token, user_id, _ = _login("faculty", org_id, dept_id)
    document_id = _generated_document(token, _template(user_id, org_id, dept_id))

    routes = [
        (f"/documents/{document_id}/download?format=docx", "docx", "Budget.docx"),
        (f"/documents/{document_id}/download/pdf", "pdf", "Budget.pdf"),
        (f"/documents/{document_id}/versions/1/download/pdf", "pdf", "Budget v1.pdf"),
    ]
    for path, fmt, _name in routes:
        response = client.get(f"{API}{path}", headers=_auth(token))
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
    with TestSession() as db:
        rows = list(db.scalars(select(DownloadHistory).where(DownloadHistory.document_id == document_id)
                               .order_by(DownloadHistory.id)))
    assert [(r.format, r.version, r.version_source, r.user_id) for r in rows] == [
        ("docx", 1, "generated", user_id), ("pdf", 1, "generated", user_id), ("pdf", 1, "generated", user_id)
    ]
    assert rows[1].file_size == len(FAKE_PDF) and rows[0].file_name.endswith(".docx")
    assert rows[0].document_name == "Budget" and rows[0].ip_address == "testclient"
    downloads = _audit("document.download", document_id)
    assert len(downloads) == 3
    assert (downloads[0].organization_id, downloads[0].department_id) == (org_id, dept_id)
    assert "Downloaded DOCX of 'Budget' v1" == downloads[0].summary

    other_token, _, _ = _login()
    before = _count(DownloadHistory)
    assert client.get(f"{API}/documents/{document_id}/download/pdf", headers=_auth(other_token)).status_code == 403
    assert client.get(f"{API}/documents/{document_id}/versions/9/download/pdf", headers=_auth(token)).status_code == 404
    assert client.get(f"{API}/documents/999999/download?format=docx", headers=_auth(token)).status_code == 404
    with TestSession() as db:  # no PDF -> 409
        from app.models.generated_file import GeneratedFile
        record = db.scalars(select(GeneratedFile).where(GeneratedFile.document_id == document_id)).one()
        record.pdf_path = None
        db.commit()
    assert client.get(f"{API}/documents/{document_id}/download/pdf", headers=_auth(token)).status_code == 409
    assert _count(DownloadHistory) == before
    assert len(_audit("document.download", document_id)) == 3


def test_my_downloads_and_document_downloads():
    token, user_id, _ = _login()
    document_id = _generated_document(token, _template(user_id))
    client.get(f"{API}/documents/{document_id}/download?format=docx", headers=_auth(token))
    client.get(f"{API}/documents/{document_id}/download/pdf", headers=_auth(token))
    other_token, _, _ = _login()

    mine = client.get(f"{API}/me/downloads?limit=1", headers=_auth(token)).json()
    assert mine["total"] == 2 and mine["page"] == 1 and len(mine["items"]) == 1
    item = mine["items"][0]
    assert (item["format"], item["document_id"], item["document_exists"], item["version"]) == (
        "pdf", document_id, True, 1
    )
    assert client.get(f"{API}/me/downloads?format=docx", headers=_auth(token)).json()["total"] == 1
    assert client.get(f"{API}/me/downloads", headers=_auth(other_token)).json()["total"] == 0
    assert client.get(f"{API}/me/downloads?limit=500", headers=_auth(token)).status_code == 422

    history = client.get(f"{API}/documents/{document_id}/downloads", headers=_auth(token))
    assert history.status_code == 200 and history.json()["total"] == 2
    assert client.get(f"{API}/documents/{document_id}/downloads", headers=_auth(other_token)).status_code == 403
    assert client.get(f"{API}/documents/999999/downloads", headers=_auth(token)).status_code == 404


# ── P2.1 editor ──────────────────────────────────────────────────


def _callback(key: str, payload: dict):
    payload = {"key": key, **payload}
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    return TestClient(app).post(f"{API}/editor/callback/{key}", json={**payload, "token": token})


def test_editor_actions_are_audited_and_file_fetches_are_not_downloads(fakes):
    token, user_id, _ = _login("faculty")
    admin_token, admin_id, _ = _login("org_admin")
    template_id = _template(admin_id)
    copy = client.post(f"{API}/templates/{template_id}/customize", headers=_auth(token))
    assert copy.status_code == 201
    customized = _audit("template.customize", copy.json()["id"])
    assert len(customized) == 1 and json.loads(customized[0].details) == {"parent_template_id": template_id}

    document_id = _generated_document(token, template_id)
    opened = client.post(f"{API}/documents/{document_id}/editor-session", headers=_auth(token)).json()
    again = client.post(f"{API}/documents/{document_id}/editor-session", headers=_auth(token)).json()
    assert again["reused"] is True
    assert len(_audit("editor.session_open", document_id)) == 1  # not again for the reused session

    before = _count(DownloadHistory)
    url = urlsplit(opened["config"]["document"]["url"])
    assert TestClient(app).get(f"{url.path}?{url.query}").status_code == 200
    assert _count(DownloadHistory) == before

    key = opened["session_key"]
    assert _callback(key, {"status": 2, "url": fakes.publish(docx("Title: by hand"))}).json() == {"error": 0}
    edits = _audit("document.file_edit", document_id)
    assert len(edits) == 1 and edits[0].ip_address is None and edits[0].actor_id == user_id
    assert json.loads(edits[0].details)["version"] == 2 and json.loads(edits[0].details)["base_version"] == 1

    client.get(f"{API}/documents/{document_id}/versions/2/download/docx", headers=_auth(token))
    with TestSession() as db:
        last = db.scalars(select(DownloadHistory).order_by(DownloadHistory.id.desc())).first()
    assert (last.version, last.version_source) == (2, "manual_edit")

    # Regenerating over the manual version is flagged.
    client.post(f"{API}/documents/{document_id}/generate?replace_manual_edits=true", headers=_auth(token))
    generated = _audit("document.generate", document_id)
    assert json.loads(generated[-1].details)["replaced_manual_edits"] is True

    # A rejected file (not a DOCX) -> editor.save_failed without contents.
    failing = client.post(f"{API}/documents/{document_id}/editor-session?version=3", headers=_auth(token)).json()
    assert _callback(failing["session_key"], {"status": 2, "url": fakes.publish(b"not a docx", "x.docx")}).json() == {
        "error": 1
    }
    failed = _audit("editor.save_failed", document_id)
    assert len(failed) == 1 and "not a docx" not in (failed[0].details or "")


# ── Hooks ────────────────────────────────────────────────────────


def test_hooks_record_safe_details(monkeypatch):
    org_id, dept_id = _org_and_dept()
    token, user_id, email = _login("faculty", org_id, dept_id)

    upload = client.post(
        f"{API}/templates/upload",
        files={"file": ("mom.docx", io.BytesIO(docx("Title: {{ title }}")), DOCX_TYPE)},
        data={"name": "Uploaded MoM", "category": "mom", "visibility": "private"},
        headers=_auth(token),
    )
    assert upload.status_code == 201, upload.text
    uploaded_id = upload.json()["id"]
    assert len(_audit("template.upload", uploaded_id)) == 1

    synced = client.put(f"{API}/templates/{uploaded_id}/fields",
                        json={"fields": [{"field_name": "title", "field_type": "text"}]}, headers=_auth(token))
    assert synced.status_code == 200, synced.text
    fields = _audit("template.fields_update", uploaded_id)
    assert json.loads(fields[-1].details)["created"] == 1

    template_id = _template(user_id, org_id, dept_id)
    document_id = _generated_document(token, template_id)
    saved = _audit("document.values_update", document_id)
    assert json.loads(saved[0].details) == {"changed_count": 1, "changed_fields": ["title"], "saved_count": 1}
    assert len(_audit("document.create", document_id)) == 1
    assert json.loads(_audit("document.generate", document_id)[0].details)["version"] == 1

    monkeypatch.setattr(ai_service, "model_for_action", lambda action: "fake-model")
    monkeypatch.setattr(ai_service, "improve_text", lambda action, text: text + " (formal)")
    improved = client.post(f"{API}/ai/improve-text", headers=_auth(token), json={
        "template_id": template_id, "document_id": document_id, "field_name": "title",
        "action_type": "formal", "original_text": SENTINEL,
    })
    assert improved.status_code == 200, improved.text
    ai_rows = _audit("ai.improve_text", document_id)
    assert json.loads(ai_rows[0].details)["status"] == "success" and json.loads(ai_rows[0].details)["ai_generation_id"]

    with TestSession() as db:
        details = " ".join(row.details or "" for row in db.scalars(select(AuditLog)))
    assert SENTINEL not in details  # field values never reach the audit log

    super_token, _, _ = _login("super_admin")
    target_token, target_id, _ = _login("faculty")
    updated = client.patch(f"{API}/admin/users/{target_id}", json={"role": "approver"}, headers=_auth(super_token))
    assert updated.status_code == 200, updated.text
    change = _audit("admin.user_update", target_id)
    assert json.loads(change[0].details)["changed"] == {"role": ["faculty", "approver"]}

    logins = _audit("auth.login", user_id)
    assert logins and logins[0].actor_email == email
    bad = client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401
    failed = _audit("auth.login_failed")
    assert failed[-1].actor_id is None and failed[-1].actor_email == email and failed[-1].summary == "Failed login"
    assert "wrong-password" not in (failed[-1].details or "")


def test_logout_is_audited():
    session = TestClient(app)
    session.post(f"{API}/auth/signup", json={"full_name": "Out", "email": "p3_out@example.com",
                                             "password": "strong-password"})
    assert session.post(f"{API}/auth/login", json={"email": "p3_out@example.com",
                                                    "password": "strong-password"}).status_code == 200
    assert session.post(f"{API}/auth/logout", headers={"X-Requested-With": "TemplateOS"}).status_code == 204
    assert _audit("auth.logout")[-1].actor_email == "p3_out@example.com"


def test_audit_failure_never_breaks_the_action(monkeypatch):
    token, user_id, _ = _login()
    template_id = _template(user_id)
    document = client.post(f"{API}/documents/create", json={"template_id": template_id}, headers=_auth(token)).json()

    def broken(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(audit_service, "add_audit_log", broken)
    saved = client.put(f"{API}/documents/{document['id']}/values",
                       json={"values": [{"field_name": "title", "value": "Kept"}]}, headers=_auth(token))
    assert saved.status_code == 200, saved.text
    with TestSession() as db:
        from app.models.document_value import DocumentValue
        value = db.scalars(select(DocumentValue).where(DocumentValue.document_id == document["id"])).one()
    assert value.value == "Kept"
    assert _audit("document.values_update", document["id"]) == []

    generated = client.post(f"{API}/documents/{document['id']}/generate", headers=_auth(token))
    assert generated.status_code == 200
    assert client.get(f"{API}/documents/{document['id']}/download/pdf", headers=_auth(token)).status_code == 200
    assert _count(DownloadHistory, DownloadHistory.document_id == document["id"]) == 1


# ── Audit log API ────────────────────────────────────────────────


def test_audit_log_scoping_filters_and_export():
    org_id, dept_id = _org_and_dept()
    other_org, other_dept = _org_and_dept()
    with TestSession() as db:
        for org, dept, summary in [
            (org_id, dept_id, "=HYPERLINK(\"x\") in dept"),
            (org_id, None, "org level"),
            (other_org, other_dept, "other org"),
        ]:
            audit_log_crud.add_audit_log(db, actor=None, action="template.upload", entity_type="template",
                                         entity_id=1, summary=summary, organization_id=org, department_id=dept)
        db.commit()

    super_token, _, _ = _login("super_admin")
    org_token, _, _ = _login("org_admin", org_id)
    dept_token, _, _ = _login("department_admin", org_id, dept_id)
    faculty_token, _, _ = _login("faculty", org_id, dept_id)

    def summaries(token: str, query: str = "") -> list[str]:
        response = client.get(f"{API}/admin/audit-logs?action=template.upload&limit=100{query}", headers=_auth(token))
        assert response.status_code == 200, response.text
        return [item["summary"] for item in response.json()["items"]]

    assert {"other org", "org level"} <= set(summaries(super_token))
    assert set(summaries(org_token)) == {"=HYPERLINK(\"x\") in dept", "org level"}
    assert summaries(dept_token) == ["=HYPERLINK(\"x\") in dept"]
    assert client.get(f"{API}/admin/audit-logs", headers=_auth(faculty_token)).status_code == 403
    assert client.get(f"{API}/admin/audit-logs/actions", headers=_auth(faculty_token)).status_code == 403
    assert summaries(org_token, "&q=ORG LEVEL") == ["org level"]

    actions = client.get(f"{API}/admin/audit-logs/actions", headers=_auth(dept_token)).json()
    assert {"action": "editor.session_open", "label": "Editor opened", "area": "editor"} in actions

    assert client.get(f"{API}/admin/audit-logs?from=2026-05-02&to=2026-05-01", headers=_auth(super_token)).status_code == 422
    assert client.get(f"{API}/admin/audit-logs?from=2025-01-01&to=2026-05-01", headers=_auth(super_token)).status_code == 422
    assert client.get(f"{API}/admin/audit-logs?action=nope", headers=_auth(super_token)).status_code == 422
    today = client.get(f"{API}/admin/audit-logs?from=2000-01-01&to=2000-12-31", headers=_auth(super_token))
    assert today.status_code == 200 and today.json()["total"] == 0

    export = client.get(f"{API}/admin/audit-logs/export.csv?action=template.upload", headers=_auth(org_token))
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"audit-log-" in export.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(export.text.lstrip("﻿"))))
    assert rows[0][0] == "time_utc" and len(rows) == 3
    assert {row[5] for row in rows[1:]} == {"'=HYPERLINK(\"x\") in dept", "org level"}
    exported = _audit("admin.audit_export")
    assert json.loads(exported[-1].details)["rows"] == 2
    assert client.get(f"{API}/admin/audit-logs/export.csv", headers=_auth(faculty_token)).status_code == 403
