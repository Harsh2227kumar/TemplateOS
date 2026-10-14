"""
CRUD helpers for generated_files (V1.6).

- get_generated_file          -> lookup by document
- upsert_generated_file       -> POST /documents/{id}/generate (replace on regenerate)
- update_pdf_result           -> POST /documents/{id}/generate-pdf (retry)
- get_generated_files_for_documents -> list view enrichment

The write helpers do NOT commit; the caller commits once together with the
document status change, then removes the superseded files they return.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    pdf_path: str | None,
    pdf_error: str | None,
    generated_at: datetime,
    template_version: int | None = None,
    template_source_path: str | None = None,
) -> tuple[GeneratedFile, list[str]]:
    """
    Create or replace the document's generated_files row (not committed).

    Returns (row, superseded paths): the previous DOCX/PDF paths that are no
    longer referenced, for the caller to delete from storage after commit.
    """
    record = get_generated_file(db, document_id)
    superseded: list[str] = []
    if record is None:
        record = GeneratedFile(document_id=document_id, docx_path=docx_path)
        db.add(record)
    else:
        for old in (record.docx_path, record.pdf_path):
            if old and old not in (docx_path, pdf_path):
                superseded.append(old)
    record.docx_path = docx_path
    record.pdf_path = pdf_path
    record.pdf_error = None if pdf_path else _clip_error(pdf_error)
    record.generated_at = generated_at
    record.template_version = template_version
    record.template_source_path = template_source_path
    db.flush()
    return record, superseded


def update_pdf_result(
    db: Session,
    record: GeneratedFile,
    *,
    pdf_path: str | None,
    pdf_error: str | None,
) -> list[str]:
    """
    Record a PDF (re)conversion outcome on an existing row (not committed).

    A successful conversion replaces any previous PDF. On failure (or "not
    configured", pdf_error None) an existing PDF is kept: it was converted
    from this same DOCX, so it is still a valid copy. Returns the superseded
    paths to delete after commit.
    """
    superseded: list[str] = []
    if pdf_path:
        if record.pdf_path and record.pdf_path != pdf_path:
            superseded.append(record.pdf_path)
        record.pdf_path = pdf_path
        record.pdf_error = None
    else:
        record.pdf_error = _clip_error(pdf_error)
    db.flush()
    return superseded
