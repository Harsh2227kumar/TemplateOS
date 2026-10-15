"""
CRUD helpers for generated_files (V1.6).

- get_generated_file          -> lookup by document
- upsert_generated_file       -> POST /documents/{id}/generate (replace on
                                 regenerate, PDF state reset to "pending");
                                 not committed: the caller commits it with
                                 the document status change, then removes
                                 the superseded files it returns
- mark_pdf_converted / mark_pdf_failed -> record a conversion outcome
                                 (generate and POST /generate-pdf); commit
- get_generated_files_for_documents -> list view enrichment
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive
from app.models.generated_file import PDF_ERROR_MAX_LENGTH, GeneratedFile


def _clip_error(error: str | None) -> str | None:
    if not error:
        return None
    error = error.strip()
    if len(error) > PDF_ERROR_MAX_LENGTH:
        error = error[: PDF_ERROR_MAX_LENGTH - 3] + "..."
    return error or None


def get_generated_file(db: Session, document_id: int) -> GeneratedFile | None:
    return db.execute(
        select(GeneratedFile).where(GeneratedFile.document_id == document_id)
    ).scalar_one_or_none()


def get_generated_files_for_documents(
    db: Session, document_ids: list[int]
) -> dict[int, GeneratedFile]:
    if not document_ids:
        return {}
    rows = db.execute(
        select(GeneratedFile).where(GeneratedFile.document_id.in_(document_ids))
    ).scalars()
    return {row.document_id: row for row in rows}


def upsert_generated_file(
    db: Session,
    document_id: int,
    *,
    docx_path: str,
    generated_at: datetime,
    template_version: int | None = None,
    template_source_path: str | None = None,
) -> tuple[GeneratedFile, list[str]]:
    """
    Create or replace the document's generated_files row (not committed).

    The PDF state is reset for the new DOCX: pdf_status "pending", no PDF,
    no error, pdf_attempts 0. Returns (row, superseded paths): the previous
    DOCX/PDF paths, for the caller to delete from storage after commit.
    """
    record = get_generated_file(db, document_id)
    superseded: list[str] = []
    if record is None:
        record = GeneratedFile(document_id=document_id, docx_path=docx_path)
        db.add(record)
    else:
        for old in (record.docx_path, record.pdf_path):
            if old and old != docx_path:
                superseded.append(old)
    record.docx_path = docx_path
    record.pdf_path = None
    record.pdf_error = None
    record.pdf_status = "pending"
    record.pdf_converted_at = None
    record.pdf_attempts = 0
    record.generated_at = generated_at
    record.template_version = template_version
    record.template_source_path = template_source_path
    db.flush()
    return record, superseded


def mark_pdf_converted(
    db: Session, generated_file: GeneratedFile, pdf_path: str
) -> GeneratedFile:
    """
    Record a successful conversion (commits). The caller removes a replaced
    earlier PDF from storage.
    """
    generated_file.pdf_path = pdf_path
    generated_file.pdf_status = "converted"
    generated_file.pdf_error = None
    generated_file.pdf_converted_at = utc_now_naive()
    generated_file.pdf_attempts = (generated_file.pdf_attempts or 0) + 1
    db.commit()
    db.refresh(generated_file)
    return generated_file


def mark_pdf_failed(
    db: Session, generated_file: GeneratedFile, error: str
) -> GeneratedFile:
    """
    Record a failed conversion (commits). An existing pdf_path is KEPT: it was
    converted from this same DOCX, so a failed retry must not hide it.
    """
    generated_file.pdf_status = "failed"
    generated_file.pdf_error = _clip_error(error) or "PDF conversion failed"
    generated_file.pdf_attempts = (generated_file.pdf_attempts or 0) + 1
    db.commit()
    db.refresh(generated_file)
    return generated_file
