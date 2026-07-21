import os
from pathlib import Path
from typing import Iterator

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-storage-tests")

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.storage import get_storage_service
from app.main import app
from app.models.user import User
from app.services.storage_service import LocalStorageService


@pytest.fixture()
def storage_client(tmp_path: Path) -> Iterator[tuple[TestClient, LocalStorageService]]:
    service = LocalStorageService(tmp_path)
    user = User(
        id=1,
        email="yash@example.com",
        full_name="Yash Khadgi",
        role="normal_user",
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_storage_service] = lambda: service

    with TestClient(app) as client:
        yield client, service

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_storage_service, None)


def test_upload_original_template_saves_docx(
    storage_client: tuple[TestClient, LocalStorageService],
) -> None:
    client, service = storage_client

    response = client.post(
        "/api/v1/storage/templates/original",
        files={
            "file": (
                "Meeting Notes.DOCX",
                b"docx-content",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["path"].startswith("templates/original/meeting-notes-")
    assert body["path"].endswith(".docx")
    assert body["filename"].endswith(".docx")
    assert body["size_bytes"] == len(b"docx-content")
    assert body["content_type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert service.read_bytes(body["path"]) == b"docx-content"


def test_upload_original_template_rejects_non_docx(
    storage_client: tuple[TestClient, LocalStorageService],
) -> None:
    client, _ = storage_client

    response = client.post(
        "/api/v1/storage/templates/original",
        files={"file": ("notes.txt", b"text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only DOCX files can be uploaded"


def test_upload_original_template_rejects_empty_file(
    storage_client: tuple[TestClient, LocalStorageService],
) -> None:
    client, _ = storage_client

    response = client.post(
        "/api/v1/storage/templates/original",
        files={
            "file": (
                "empty.docx",
                b"",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_upload_original_template_requires_auth(tmp_path: Path) -> None:
    service = LocalStorageService(tmp_path)
    app.dependency_overrides[get_storage_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/storage/templates/original",
            files={
                "file": (
                    "meeting.docx",
                    b"docx-content",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    app.dependency_overrides.pop(get_storage_service, None)

    assert response.status_code == 401
