"""
Document version endpoints (V1.7 Phase 2). Owner only, like the preview.

Every POST /documents/{id}/generate creates a version (see
app.services.document_generation). These routes list, show, download and
restore them:

- GET  /documents/{document_id}/versions                       newest first
- GET  /documents/{document_id}/versions/{version}             values (snapshot)
- GET  /documents/{document_id}/versions/{version}/download/docx
- GET  /documents/{document_id}/versions/{version}/download/pdf
- POST /documents/{document_id}/versions/{version}/restore     snapshot -> draft

Downloads: 404 unknown version, 410 when retention removed the files or the
file is missing on disk, 409 when the version has no PDF. The latest-version
downloads (GET /documents/{id}/download) are unchanged.
"""

import logging
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.documents import MEDIA_TYPES, annotate_sections, document_read
from app.crud.document_crud import get_document_by_id
from app.crud.document_version_crud import (
    changed_fields_by_version,
    diff_snapshots,
    get_version,
    latest_version_number,
    list_versions,
    parse_snapshot,
    restore_values,
)
from app.crud.template_field_crud import get_fields_by_template
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.schemas.document import DocumentRead
from app.schemas.document_version import DocumentVersionDetail, DocumentVersionRead
from app.services import document_generation
from app.services.document_permissions import document_permissions, require_document_viewer
from app.services.document_preview import build_sections
from app.services.generation_service import format_field_value
from app.services.storage_service import storage_service

router = APIRouter()
logger = logging.getLogger(__name__)

DELETED_USER = "Deleted user"
NOT_EDITABLE = "This document can no longer be edited, so a version cannot be restored"


def _viewable_document(db, document_id: int, user: User) -> Document:
    """404 when missing, 403 unless the user may view it (owner)."""
    document = get_document_by_id(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    require_document_viewer(user, document)
    return document


def _version_or_404(db, document: Document, number: int) -> DocumentVersion:
    version = get_version(db, document.id, number)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {number} does not exist"
        )
    return version


def version_read(
    document: Document,
    version: DocumentVersion,
    changed_fields: list[str],
    is_latest: bool,
) -> DocumentVersionRead:
    record = version.generated_file
    pruned = record is not None and record.files_pruned
    has_docx = bool(record) and not pruned and document_generation.stored_file_available(record.docx_path)
    has_pdf = bool(record) and not pruned and document_generation.stored_file_available(record.pdf_path)
    creator = version.creator
    return DocumentVersionRead(
        version=version.version,
        created_at=version.created_at,
        created_by_name=(creator.full_name or creator.email) if creator else DELETED_USER,
        template_version=version.template_version,
        pdf_status=record.pdf_status if record else None,
        pdf_error=record.pdf_error if record else None,
        has_docx=has_docx,
        has_pdf=has_pdf,
        files_pruned=pruned,
        changed_fields=changed_fields,
        is_latest=is_latest,
        docx_url=(
            document_generation.version_download_url(document.id, version.version, "docx")
            if has_docx
            else None
        ),
        pdf_url=(
            document_generation.version_download_url(document.id, version.version, "pdf")
            if has_pdf
            else None
        ),
    )


def snapshot_fields(template_fields, snapshot: list[dict]) -> list:
    """
    The fields a version view shows: the template's fields, plus fields
    that were in the snapshot but are no longer in the template (shown as a
    textarea / text field after the others, labelled by name), so an old
    version keeps every value it was generated from.
    """
    fields = list(template_fields)
    known = {field.field_name for field in fields}
    last_order = max((field.display_order or 0 for field in fields), default=0)
    for offset, item in enumerate(item for item in snapshot if item["field_name"] not in known):
        fields.append(
            SimpleNamespace(
                id=10**9 + offset,
                field_name=item["field_name"],
                field_label=None,
                field_type="textarea" if item["value_format"] == "rich" else "text",
                is_required=False,
                ai_enabled=False,
                display_order=last_order + 1 + offset,
                section=None,
            )
        )
    return fields


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionRead],
    responses={403: {"description": "Not the owner"}, 404: {"description": "Document not found"}},
    summary="List the document's versions, newest first",
)
def list_document_versions(db: DbSession, current_user: CurrentUser, document_id: int):
    """
    Every generated version (newest first) with who generated it, the PDF
    state, whether its files can still be downloaded (has_docx / has_pdf,
    files_pruned after retention) and the fields changed since the previous
    version. Empty until the first generate.
    """
    document = _viewable_document(db, document_id, current_user)
    versions = list_versions(db, document.id)
    changed = changed_fields_by_version(versions)
    latest = versions[0].version if versions else None
    return [
        version_read(document, version, changed[version.version], version.version == latest)
        for version in versions
    ]


@router.get(
    "/{document_id}/versions/{version}",
    response_model=DocumentVersionDetail,
    responses={403: {"description": "Not the owner"}, 404: {"description": "Unknown version"}},
    summary="One version with the values it was generated from",
)
def get_document_version(db: DbSession, current_user: CurrentUser, document_id: int, version: int):
    """
    The version's metadata plus its values as preview sections, built from
    the version's own snapshot (formatted like the generated document; rich
    values include their Tiptap JSON). Still available after retention
    removed the files.
    """
    document = _viewable_document(db, document_id, current_user)
    record = _version_or_404(db, document, version)
    snapshot = parse_snapshot(record)
    previous = get_version(db, document.id, version - 1) if version > 1 else None
    changed = diff_snapshots(parse_snapshot(previous) if previous else None, snapshot)
    latest = latest_version_number(db, document.id)
    items = {item["field_name"]: item for item in snapshot}
    fields = snapshot_fields(get_fields_by_template(db, document.template_id), snapshot)
    sections = build_sections(
        fields,
        {name: item["value"] for name, item in items.items()},
        format_value=format_field_value,
    )
    return DocumentVersionDetail(
        **version_read(document, record, changed, record.version == latest).model_dump(),
        document_id=document.id,
        sections=annotate_sections(sections, items),
    )


@router.get(
    "/{document_id}/versions/{version}/download/{file_format}",
    response_class=FileResponse,
    responses={
        403: {"description": "Not the owner"},
        404: {"description": "Unknown version"},
        409: {"description": "No PDF for this version"},
        410: {"description": "The version's files were removed (retention) or are missing"},
    },
    summary="Download one version's DOCX or PDF",
)
def download_document_version(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    version: int,
    file_format: Literal["docx", "pdf"],
):
    """
    Stream a version's file as "<draft name> v<n>.<ext>" (owner only).
    410 when retention removed the version's files (its values stay
    viewable) or the file is missing on disk; 409 when it has no PDF.
    """
    document = _viewable_document(db, document_id, current_user)
    record = _version_or_404(db, document, version).generated_file
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} has no generated files"
        )
    if record.files_pruned:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"The files of version {version} were removed to save space. "
                "Its values are still available: restore them and generate again."
            ),
        )
    stored = record.docx_path if file_format == "docx" else record.pdf_path
    if file_format == "pdf" and not stored:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version {version} has no PDF",
        )
    if not document_generation.stored_file_available(stored):
        logger.warning("Version %s of document %s: %s missing on disk", version, document.id, file_format)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"The {file_format.upper()} of version {version} is missing on the server",
        )
    filename = document_generation.version_filename(document, version, file_format)
    return FileResponse(
        storage_service.file_path(stored),
        media_type=MEDIA_TYPES[file_format],
        headers={
            "Content-Disposition": document_generation.content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/{document_id}/versions/{version}/restore",
    response_model=DocumentRead,
    responses={
        403: {"description": "Not the owner"},
        404: {"description": "Unknown version"},
        409: {"description": "The document is not editable"},
    },
    summary="Replace the draft's values with a version's values",
)
def restore_document_version(db: DbSession, current_user: CurrentUser, document_id: int, version: int):
    """
    Copy the version's snapshot into the draft's current values (fields not
    in the snapshot are cleared) and return the document. Does not
    generate: the next Generate creates a new version. 409 when the
    document can no longer be edited (e.g. submitted).
    """
    document = _viewable_document(db, document_id, current_user)
    if not document_permissions(current_user, document).can_edit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_EDITABLE)
    record = _version_or_404(db, document, version)
    restore_values(db, document, record)
    db.commit()
    logger.info("Restored version %s into document %s by user %s", version, document.id, current_user.id)
    return document_read(db, get_document_by_id(db, document.id, include_values=True))
