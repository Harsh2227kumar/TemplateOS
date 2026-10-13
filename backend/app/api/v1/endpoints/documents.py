"""
Document endpoints for V1.4 Phase 2 — Save Draft functionality.

Endpoints:
- POST /documents/create
- PUT /documents/{document_id}/values
- GET /documents
- GET /documents/{document_id}
- GET /documents/{document_id}/values

V1.6 generation (owner only):
- POST /documents/{document_id}/generate      render DOCX (+ PDF if configured)
- POST /documents/{document_id}/generate-pdf  retry the PDF conversion only
- GET  /documents/{document_id}/download?format=docx|pdf
"""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.crud.document_crud import (
    create_document,
    get_document_by_id,
    get_documents_by_user,
)
from app.crud.document_value_crud import get_values_by_document, upsert_values
from app.crud.generated_file_crud import (
    get_generated_file,
    get_generated_files_for_documents,
)
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import get_fields_by_template
from app.models.document import Document
from app.models.template import Template
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentRead,
    DocumentValidationErrorResponse,
    DocumentValuesBulkRead,
    DocumentValuesBulkUpsert,
    GenerateDocumentResponse,
)
from app.services import document_generation
from app.services.document_validator import validate_document_values
from app.services.storage_service import StorageError, storage_service
from app.services.template_access import user_can_view_template

router = APIRouter()
logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


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
    - Validates against template fields: required, type (number, list),
      validation_rule (email, min:N, max:N); 422 detail is [{field_name, error}]
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

    # Validate values
    values_to_save = [v.model_dump() for v in payload.values]
    try:
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
        values=[
            {
                "id": v.id,
                "document_id": v.document_id,
                "field_name": v.field_name,
                "value": v.value,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
            }
            for v in saved_values
        ],
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

    # Build response with values
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
        values=[
            {
                "id": v.id,
                "document_id": v.document_id,
                "field_name": v.field_name,
                "value": v.value,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
            }
            for v in document.values
        ],
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
        values=[
            {
                "id": v.id,
                "document_id": v.document_id,
                "field_name": v.field_name,
                "value": v.value,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
            }
            for v in values
        ],
    )


# ── V1.6 generation ──────────────────────────────────────────────


@router.post(
    "/{document_id}/generate",
    response_model=GenerateDocumentResponse,
    responses={422: {"model": DocumentValidationErrorResponse}},
    summary="Generate the DOCX (and PDF when configured) from the saved values",
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
    - Regenerating replaces the previous DOCX/PDF
    - A PDF failure never fails this call: see pdf_status / pdf_error
    - Sets the document status to "generated"
    """
    document = _get_owned_document(db, document_id, current_user, include_values=True)
    template = get_template_by_id(db, document.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    record = document_generation.generate_document(db, document, template)
    return document_generation.generation_response(document, record)


@router.post(
    "/{document_id}/generate-pdf",
    response_model=GenerateDocumentResponse,
    summary="Retry the PDF conversion of the generated DOCX",
)
def retry_pdf_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
):
    """
    Convert the last generated DOCX to PDF again (owner only). 404 when the
    document has not been generated. Always 200 otherwise: the outcome is
    in pdf_status (ok / failed / not_configured).
    """
    document = _get_owned_document(db, document_id, current_user)
    record = document_generation.retry_pdf(db, document)
    return document_generation.generation_response(document, record)


@router.get(
    "/{document_id}/download",
    response_class=FileResponse,
    summary="Download the generated DOCX or PDF",
)
def download_document(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    format: Literal["docx", "pdf"] = Query("docx"),
):
    """
    Stream the generated file as an attachment named after the draft.
    404 when the document has not been generated; 409 when the PDF is not
    available (failed / not configured) or the stored file is missing.
    """
    document = _get_owned_document(db, document_id, current_user)
    record = get_generated_file(db, document.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The document has not been generated yet",
        )
    relative_path = record.docx_path if format == "docx" else record.pdf_path
    if not relative_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The PDF is not available for this document",
        )
    try:
        path = storage_service.file_path(relative_path)
    except StorageError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The generated file is missing; generate the document again",
        ) from None
    filename = document_generation.download_filename(document, format)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": document_generation.content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )
