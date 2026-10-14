"""
Document generation orchestration (V1.6): validate -> render DOCX -> store ->
convert PDF (optional) -> record -> remove superseded files.

Called from the plain `def` endpoints in app/api/v1/endpoints/documents.py,
so this blocking work runs in FastAPI's threadpool.
"""

import logging
import re
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive
from app.core.config import settings
from app.crud.generated_file_crud import (
    get_generated_file,
    update_pdf_result,
    upsert_generated_file,
)
from app.crud.template_field_crud import get_fields_by_template
from app.models.document import Document
from app.models.generated_file import GeneratedFile
from app.models.template import Template
from app.schemas.document import GeneratedInfo, GenerateDocumentResponse
from app.services.document_validator import validate_document_values
from app.services.docx_cleaner import get_renderable_path
from app.services.generated_file_cleanup import delete_stored_files
from app.services.generation_service import (
    TemplateRenderError,
    build_context,
    render_docx,
)
from app.services.pdf_service import PdfConversionError, get_pdf_converter
from app.services.storage_service import (
    StorageError,
    StoredFileNotFoundError,
    storage_service,
)

logger = logging.getLogger(__name__)

# Statuses that generation moves to "generated"; later workflow statuses
# (submitted, approved, ...) are left alone.
_GENERATABLE_STATUSES = ("draft", "generated")
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w\s().,-]+", re.UNICODE)
MAX_FILENAME_STEM = 100


def download_filename(document: Document, extension: str) -> str:
    """
    A safe download filename from the draft name, e.g.
    "Weekly MoM: 13/10" -> "Weekly MoM 13 10.docx". Falls back to
    "document-<id>" when nothing usable is left.
    """
    name = _UNSAFE_FILENAME_CHARS.sub(" ", document.name or "")
    name = re.sub(r"\s+", " ", name).strip(" .-_")[:MAX_FILENAME_STEM].strip()
    return f"{name or f'document-{document.id}'}.{extension}"


def content_disposition(filename: str) -> str:
    """
    attachment header with a plain ASCII `filename` (non-ASCII -> "_") for
    old clients plus the exact UTF-8 name in `filename*` (RFC 6266).
    """
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def download_url(document_id: int, file_format: str) -> str:
    return f"{settings.api_v1_prefix}/documents/{document_id}/download?format={file_format}"


def generated_info(document: Document, record: GeneratedFile | None) -> GeneratedInfo | None:
    if record is None:
        return None
    return GeneratedInfo(
        generated_at=record.generated_at,
        pdf_status=record.pdf_status,
        pdf_error=record.pdf_error,
        docx_url=download_url(document.id, "docx"),
        pdf_url=download_url(document.id, "pdf") if record.pdf_path else None,
        is_stale=document.updated_at > record.generated_at,
        template_version=record.template_version,
    )


def generation_response(document: Document, record: GeneratedFile) -> GenerateDocumentResponse:
    info = generated_info(document, record)
    return GenerateDocumentResponse(
        **info.model_dump(), document_id=document.id, document_status=document.status
    )


def _validate_required(fields, values: dict[str, str]) -> None:
    """Run the save validator over EVERY field (a missing value counts as "")."""
    payload = [
        {"field_name": field.field_name, "value": values.get(field.field_name) or ""}
        for field in fields
    ]
    validate_document_values(fields, payload)


def _convert_pdf(docx_bytes: bytes, filename: str) -> tuple[str | None, str | None]:
    """(pdf_path, pdf_error); both None when no converter is configured."""
    converter = get_pdf_converter()
    if converter is None:
        return None, None
    try:
        pdf_bytes = converter.convert(docx_bytes, filename)
    except PdfConversionError as exc:
        return None, str(exc)
    except Exception:  # never let PDF problems break generation
        logger.exception("Unexpected PDF conversion failure")
        return None, "PDF conversion failed unexpectedly"
    try:
        stored = storage_service.save_bytes("generated_pdf", filename, pdf_bytes)
    except StorageError:
        logger.exception("Could not store generated PDF")
        return None, "The PDF could not be saved"
    return stored.path, None


def generate_document(db: Session, document: Document, template: Template) -> GeneratedFile:
    """Render, store and record the document's DOCX (+ PDF when configured)."""
    fields = get_fields_by_template(db, template.id)
    values = {value.field_name: value.value for value in document.values}
    _validate_required(fields, values)

    source_path = get_renderable_path(template)
    if not source_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Template has no source file"
        )
    try:
        template_bytes = storage_service.read_bytes(source_path)
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The template file is missing on the server",
        ) from None

    try:
        docx_bytes = render_docx(template_bytes, build_context(fields, values))
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=422, detail=str(exc)
        ) from None

    filename_stem = download_filename(document, "docx")[: -len(".docx")]
    try:
        stored_docx = storage_service.save_bytes(
            "generated_docx", f"{filename_stem}.docx", docx_bytes
        )
    except StorageError:
        logger.exception("Could not store generated DOCX for document %s", document.id)
        raise HTTPException(
            status_code=500, detail="Could not save the generated document"
        ) from None

    pdf_path, pdf_error = _convert_pdf(docx_bytes, f"{filename_stem}.docx")

    now = utc_now_naive()
    try:
        record, superseded = upsert_generated_file(
            db,
            document.id,
            docx_path=stored_docx.path,
            pdf_path=pdf_path,
            pdf_error=pdf_error,
            generated_at=now,
            template_version=template.version,
            template_source_path=source_path,
        )
        if document.status in _GENERATABLE_STATUSES:
            document.status = "generated"
        document.updated_at = now
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_files([stored_docx.path, pdf_path])
        raise
    db.refresh(record)
    db.refresh(document)
    delete_stored_files(superseded)
    logger.info(
        "Generated document %s (pdf=%s) from template %s v%s",
        document.id,
        record.pdf_status,
        template.id,
        template.version,
    )
    return record


def retry_pdf(db: Session, document: Document) -> GeneratedFile:
    """Convert the stored DOCX to PDF again and record the outcome."""
    record = get_generated_file(db, document.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The document has not been generated yet",
        )
    try:
        docx_bytes = storage_service.read_bytes(record.docx_path)
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The generated DOCX is missing; generate the document again",
        ) from None

    pdf_path, pdf_error = _convert_pdf(
        docx_bytes, download_filename(document, "docx")
    )
    try:
        superseded = update_pdf_result(db, record, pdf_path=pdf_path, pdf_error=pdf_error)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_files([pdf_path])
        raise
    db.refresh(record)
    delete_stored_files(superseded)
    return record
