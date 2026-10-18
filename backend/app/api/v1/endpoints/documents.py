"""
Document endpoints for V1.4 Phase 2 — Save Draft functionality.

Endpoints:
- POST /documents/create
- PUT /documents/{document_id}/values
- GET /documents
- GET /documents/{document_id}
- GET /documents/{document_id}/values

V1.7 preview (owner only, read-only):
- GET /documents/{document_id}/preview

V1.6 generation (owner only):
- POST /documents/{document_id}/generate      new version: render DOCX, then PDF
- POST /documents/{document_id}/generate-pdf  retry the PDF conversion only
- GET  /documents/{document_id}/download?format=docx|pdf  (latest version)
- GET  /documents/{document_id}/download/pdf  (same as ?format=pdf)

V1.7 Phase 2: values may be rich text (textarea fields, Tiptap JSON) and
carry AI provenance (ai_modified / ai_action). Version history lives in
document_versions.py.
"""

import logging
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.crud.document_crud import (
    create_document,
    get_document_by_id,
    get_document_for_preview,
    get_documents_by_user,
)
from app.crud.document_value_crud import get_values_by_document, upsert_values
from app.crud.document_version_crud import count_versions
from app.crud.generated_file_crud import (
    get_generated_file,
    get_generated_files_for_documents,
)
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import get_fields_by_template
from app.models.document import Document
from app.models.generated_file import GeneratedFile
from app.models.template import Template
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentRead,
    DocumentValidationErrorResponse,
    DocumentValueRead,
    DocumentValuesBulkRead,
    DocumentValuesBulkUpsert,
    GenerateDocumentResponse,
)
from app.schemas.document_preview import (
    DocumentPreview,
    PreviewDocument,
    PreviewGeneration,
    PreviewSection,
    PreviewTemplate,
)
from app.services import document_generation
from app.services.document_permissions import (
    document_permissions,
    require_document_viewer,
)
from app.services.document_preview import build_sections, compute_completeness
from app.services.document_validator import validate_document_values
from app.services.generation_service import format_field_value
from app.services.rich_text import RichTextError, to_plain_text, validate_rich_content
from app.services.storage_service import (
    StorageError,
    StoredFileNotFoundError,
    storage_service,
)
from app.services.template_access import user_can_view_template

router = APIRouter()
logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

RICH_ONLY_TEXTAREA = "Rich text is only available for long text fields"
RICH_CONTENT_REQUIRED = "Rich text content is missing"
AI_ACTION_REQUIRED = "ai_action is required when ai_modified is true"


def _get_owned_document(
    db, document_id: int, user: User, include_values: bool = False
) -> Document:
    """404 when missing, 403 when the current user is not the owner."""
    document = get_document_by_id(db, document_id, include_values=include_values)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    if document.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own drafts",
        )
    return document


def value_read(value) -> DocumentValueRead:
    """A saved DocumentValue as its API shape (rich_content parsed)."""
    return DocumentValueRead.model_validate(value)


def document_read(db, document: Document) -> DocumentRead:
    """GET /documents/{id} body: metadata, latest generation, saved values."""
    return DocumentRead(
        id=document.id,
        template_id=document.template_id,
        created_by=document.created_by,
        name=document.name,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        generated=document_generation.generated_info(
            document, get_generated_file(db, document.id)
        ),
        values=[value_read(v) for v in document.values],
    )


def prepare_values(fields, items) -> list[dict]:
    """
    PUT /values items as upsert dicts (V1.7 Phase 2 rules):

    - value_format "rich" only for textarea fields; rich_content is validated
      against the whitelist (app.services.rich_text) and stored normalized;
      `value` becomes its plain-text projection (the client value is ignored)
    - ai_modified true needs ai_action; false drops any ai_action

    Raises 422 [{field_name, error}] for every invalid item. Unknown fields
    are left for validate_document_values to report.
    """
    field_map = {field.field_name: field for field in fields}
    errors: list[dict] = []
    prepared: list[dict] = []
    for item in items:
        data = item.model_dump()
        name = data["field_name"]
        field = field_map.get(name)
        if data["value_format"] == "rich" and field is not None:
            if field.field_type != "textarea":
                errors.append({"field_name": name, "error": RICH_ONLY_TEXTAREA})
                continue
            if data["rich_content"] is None:
                errors.append({"field_name": name, "error": RICH_CONTENT_REQUIRED})
                continue
            try:
                data["rich_content"] = validate_rich_content(data["rich_content"])
            except RichTextError as exc:
                errors.append({"field_name": name, "error": str(exc)})
                continue
            data["value"] = to_plain_text(data["rich_content"])
        else:
            data["value_format"] = "plain"
            data["rich_content"] = None
        if data["ai_modified"] and data["ai_action"] is None:
            errors.append({"field_name": name, "error": AI_ACTION_REQUIRED})
            continue
        if not data["ai_modified"]:
            data["ai_action"] = None
        prepared.append(data)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    return prepared


@router.post(
    "/create",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new document draft from a template",
)
def create_document_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    payload: DocumentCreate,
):
    """
    Create a new document draft.

    - Validates template exists and user has view access
    - Auto-generates name if not provided: "{template.name} Draft - {timestamp}"
    - Returns DocumentRead with empty values list
    """
    # Check template exists
    template = get_template_by_id(db, payload.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Check user can view template
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this template",
        )

    # Auto-generate name if not provided
    name = payload.name
    if name is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        name = f"{template.name} Draft - {timestamp}"

    # Create document
    document = create_document(
        db=db,
        template_id=payload.template_id,
        created_by=current_user.id,
        name=name,
        status="draft",
    )

    # Return with empty values (DocumentRead expects values field)
    return DocumentRead(
        id=document.id,
        template_id=document.template_id,
        created_by=document.created_by,
        name=document.name,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        values=[],
    )


@router.put(
    "/{document_id}/values",
    response_model=DocumentValuesBulkRead,
    summary="Save/upsert form values for a document draft",
)
def save_document_values(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    payload: DocumentValuesBulkUpsert,
):
    """
    Validate and upsert field values for a document draft.

    - Enforces ownership (created_by == current_user.id)
    - Rich text (V1.7 P2): value_format "rich" + rich_content (Tiptap JSON)
      for textarea fields only; unsupported formatting -> 422 "Unsupported
      formatting: <name>"; the plain value is derived on the server
    - AI provenance: ai_modified / ai_action are stored per value
    - Validates against template fields: required, type (number, list),
      validation_rule (email, min:N, max:N; rich fields use their plain
      text); 422 detail is [{field_name, error}]
    - Bumps the document's updated_at on success
    - Returns saved values on success
    """
    logger.info(
        "Saving %d value(s) for document %s by user %s",
        len(payload.values),
        document_id,
        current_user.id,
    )

    # Load document
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Enforce ownership
    if document.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own drafts",
        )

    # Load template and fields for validation
    template = get_template_by_id(db, document.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    fields = get_fields_by_template(db, document.template_id)

    # Rich content + AI flags, then the per-field rules on the plain values
    try:
        values_to_save = prepare_values(fields, payload.values)
        validate_document_values(fields, values_to_save)
    except HTTPException as exc:
        logger.info(
            "Validation failed for document %s by user %s: %d error(s)",
            document_id,
            current_user.id,
            len(exc.detail),
        )
        raise

    # Upsert values (also bumps documents.updated_at)
    saved_values = upsert_values(db, document_id, values_to_save)
    logger.info(
        "Saved %d value(s) for document %s by user %s",
        len(saved_values),
        document_id,
        current_user.id,
    )

    # Return saved values
    return DocumentValuesBulkRead(
        document_id=document_id,
        values=[value_read(v) for v in saved_values],
    )


@router.get(
    "",
    response_model=list[DocumentListItem],
    summary="List current user's document drafts",
)
def list_user_documents(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    List all documents created by the current user.

    - Ordered by updated_at desc (newest first)
    - Includes template_name for display
    """
    documents = get_documents_by_user(db, current_user.id)

    # Enrich with template_name
    template_ids = [d.template_id for d in documents]
    templates = (
        db.execute(select(Template).where(Template.id.in_(template_ids)))
        .scalars()
        .all()
    )
    template_map = {t.id: t.name for t in templates}
    generated_map = get_generated_files_for_documents(db, [d.id for d in documents])

    return [
        DocumentListItem(
            id=d.id,
            template_id=d.template_id,
            template_name=template_map.get(d.template_id, "Unknown"),
            name=d.name,
            status=d.status,
            created_at=d.created_at,
            updated_at=d.updated_at,
            generated=document_generation.generated_info(d, generated_map.get(d.id)),
        )
        for d in documents
    ]


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get a document draft with values",
)
def get_document(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Get a document draft with its saved values.

    - Enforces ownership (created_by == current_user.id)
    - Returns DocumentRead with joined values
    """
    document = get_document_by_id(db, document_id, include_values=True)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Enforce ownership
    if document.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own drafts",
        )

    return document_read(db, document)


# ── V1.7 preview ─────────────────────────────────────────────────


def _stored_file_exists(document_id: int, relative_path: str | None, kind: str) -> bool:
    """
    True when the stored file is on disk. A stale DB row (missing file,
    path outside storage) is reported as unavailable, never as a 500. The
    warning names the document, never the path.
    """
    if not relative_path:
        return False
    if not document_generation.stored_file_available(relative_path):
        logger.warning(
            "Preview: generated %s of document %s is missing on disk", kind, document_id
        )
        return False
    return True


def _preview_generation(
    db, document: Document, record: GeneratedFile | None
) -> PreviewGeneration | None:
    """Latest generated output, with availability checked against the disk."""
    if record is None:
        return None
    pdf_available = _stored_file_exists(document.id, record.pdf_path, "PDF")
    return PreviewGeneration(
        generated_at=record.generated_at,
        is_stale=document_generation.is_stale(document, record),
        template_version=record.template_version,
        docx_available=_stored_file_exists(document.id, record.docx_path, "DOCX"),
        docx_url=document_generation.download_url(document.id, "docx"),
        pdf_status=record.pdf_status,
        pdf_error=record.pdf_error,
        pdf_available=pdf_available,
        pdf_url=document_generation.download_url(document.id, "pdf") if pdf_available else None,
        pdf_filename=PurePosixPath(record.pdf_path).name if record.pdf_path else None,
        version=record.version.version,
        versions_count=count_versions(db, document.id),
    )


def annotate_sections(sections: list[PreviewSection], items: dict[str, dict]) -> list[PreviewSection]:
    """
    Add each field's value_format / rich_content / ai_modified / ai_action
    (V1.7 P2) from `items` ({field_name: value dict}, e.g. a snapshot item).
    """
    result = []
    for section in sections:
        fields = []
        for field in section.fields:
            item = items.get(field.field_name)
            if item is None:
                fields.append(field)
                continue
            rich = item.get("value_format") == "rich" and isinstance(item.get("rich_content"), dict)
            ai_modified = bool(item.get("ai_modified"))
            fields.append(
                field.model_copy(
                    update={
                        "value_format": "rich" if rich else "plain",
                        "rich_content": item["rich_content"] if rich else None,
                        "ai_modified": ai_modified,
                        "ai_action": item.get("ai_action") if ai_modified else None,
                    }
                )
            )
        result.append(section.model_copy(update={"fields": fields}))
    return result


def value_items(values) -> dict[str, dict]:
    """document.values as {field_name: {value_format, rich_content (dict), ai_*}}."""
    return {
        value.field_name: value_read(value).model_dump(
            include={"value_format", "rich_content", "ai_modified", "ai_action"}
        )
        for value in values
    }


@router.get(
    "/{document_id}/preview",
    response_model=DocumentPreview,
    responses={
        403: {"description": "Not the owner"},
        404: {"description": "Document or template not found"},
    },
    summary="Preview a document: formatted values, completeness, generated files",
)
def get_document_preview(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
) -> DocumentPreview:
    """
    Everything the preview page needs in one read-only call (owner only).

    - sections: every template field, grouped like the edit form, with
      display_value formatted exactly like the generated document
      (generation_service.format_field_value); rich textarea values also
      carry their Tiptap JSON, and AI-written values ai_modified / ai_action
    - completeness: required fields filled vs missing
    - generation: null until generated; the latest version, its number and
      the number of versions; docx/pdf availability is checked on disk;
      URLs are API-relative, never storage paths
    - permissions: what the user may do next (document_permissions)

    Never triggers generation or PDF conversion.
    """
    document = get_document_for_preview(db, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    require_document_viewer(current_user, document)
    template = document.template
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )

    fields = list(template.fields)
    values_by_name = {value.field_name: value.value for value in document.values}
    sections = build_sections(fields, values_by_name, format_value=format_field_value)
    return DocumentPreview(
        document=PreviewDocument.model_validate(document),
        template=PreviewTemplate(
            id=template.id,
            name=template.name,
            category=template.category,
            version=template.version or 1,
            has_processed_file=bool(template.processed_file_path),
        ),
        completeness=compute_completeness(fields, values_by_name),
        sections=annotate_sections(sections, value_items(document.values)),
        generation=_preview_generation(db, document, document.generated_file),
        permissions=document_permissions(current_user, document),
    )


@router.get(
    "/{document_id}/values",
    response_model=DocumentValuesBulkRead,
    summary="Get just the values for a document draft",
)
def get_document_values(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Get the saved values for a document draft (used by edit mode).

    - Enforces ownership
    - Returns {document_id, values: list[DocumentValueRead]} (DocumentValuesBulkRead),
      without the rest of the document metadata
    """
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Enforce ownership
    if document.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own drafts",
        )

    values = get_values_by_document(db, document_id)

    return DocumentValuesBulkRead(
        document_id=document_id,
        values=[value_read(v) for v in values],
    )


# ── V1.6 generation ──────────────────────────────────────────────


@router.post(
    "/{document_id}/generate",
    response_model=GenerateDocumentResponse,
    responses={422: {"model": DocumentValidationErrorResponse}},
    summary="Generate a new version (DOCX and PDF) from the saved values",
)
def generate_document_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Render the template's processed DOCX with the draft's SAVED values.

    - Owner only (404 / 403 like the other document endpoints)
    - 422 with [{field_name, error}] when required values are missing or
      invalid (same validator and shape as saving); 422 with a string detail
      when the template itself cannot be rendered
    - 409 when the template file is missing
    - Every call creates a new version (V1.7 P2): `version` is its number,
      `versions_count` the total; older versions keep their files until
      retention (GENERATED_VERSIONS_KEEP_FILES) removes them
    - Rich textarea values render with their formatting
    - Then converts the DOCX to PDF; a PDF failure never fails this call
      (pdf_status "converted" or "failed" with pdf_error)
    - Sets the document status to "generated"
    """
    document = _get_owned_document(db, document_id, current_user, include_values=True)
    template = get_template_by_id(db, document.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    record = document_generation.generate_document(
        db, document, template, created_by=current_user.id
    )
    return document_generation.generation_response(db, document, record)


@router.post(
    "/{document_id}/generate-pdf",
    response_model=GenerateDocumentResponse,
    responses={
        404: {"description": "Not generated yet"},
        410: {"description": "The generated DOCX is missing on the server"},
        503: {"description": "PDF conversion failed; detail is the reason"},
    },
    summary="Retry the PDF conversion of the latest generated DOCX",
)
def retry_pdf_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Convert the latest version's DOCX to PDF again (owner only).

    - 200 with the generation info when the PDF is converted (also when it
      already was and the file exists: no new conversion)
    - 503 {detail: reason} when the conversion fails; the failure is recorded
      (pdf_status "failed", pdf_attempts + 1) and an earlier PDF is kept
    - 404 when the document has not been generated; 410 when the stored DOCX
      is missing on disk
    """
    document = _get_owned_document(db, document_id, current_user)
    record = document_generation.retry_pdf(db, document)
    return document_generation.generation_response(db, document, record)


def _send_generated_file(db, current_user: User, document_id: int, file_format: str):
    document = _get_owned_document(db, document_id, current_user)
    record = get_generated_file(db, document.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The document has not been generated yet",
        )
    if file_format == "docx":
        try:
            path = storage_service.file_path(record.docx_path)
        except StorageError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The generated file is missing; generate the document again",
            ) from None
    else:
        if not record.pdf_path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The PDF is not available for this document. Use Retry PDF.",
            )
        try:
            path = storage_service.file_path(record.pdf_path)
        except StoredFileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="The PDF file is missing on the server. Use Retry PDF.",
            ) from None
        except StorageError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The PDF is not available for this document. Use Retry PDF.",
            ) from None
    filename = document_generation.download_filename(document, file_format)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[file_format],
        headers={
            "Content-Disposition": document_generation.content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/{document_id}/download/pdf",
    response_class=FileResponse,
    responses={
        404: {"description": "Not generated yet"},
        409: {"description": "No PDF for this document"},
        410: {"description": "The PDF file is missing on the server"},
    },
    summary="Download the latest generated PDF",
)
def download_pdf(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Stream the latest version's PDF as an attachment named after the draft
    (owner only). 404 when not generated; 409 when there is no PDF (see
    pdf_status / pdf_error, use Retry PDF); 410 when the stored PDF is
    missing on disk.
    """
    return _send_generated_file(db, current_user, document_id, "pdf")


@router.get(
    "/{document_id}/download",
    response_class=FileResponse,
    summary="Download the latest generated DOCX or PDF",
)
def download_document(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    format: Literal["docx", "pdf"] = Query("docx"),
):
    """
    Stream the latest version's file as an attachment named after the draft.
    404 when the document has not been generated. DOCX: 409 when the stored
    file is missing. PDF (same as /download/pdf): 409 when there is no PDF,
    410 when the stored PDF is missing on disk.
    """
    return _send_generated_file(db, current_user, document_id, format)
