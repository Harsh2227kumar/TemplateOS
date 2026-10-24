"""
V1.7 Phase 2 - Document version schemas.

Response models of:
- GET /api/v1/documents/{id}/versions        -> list[DocumentVersionRead]
- GET /api/v1/documents/{id}/versions/{n}    -> DocumentVersionDetail

Contract: Prompts/V1.7-P2.md §4. As in the preview, never expose storage
paths: only API URLs (null when the file is not downloadable).
"""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel

from app.schemas.document import PdfStatus
from app.schemas.document_preview import PreviewSection

VersionSource = Literal["generated", "manual_edit"]


class DocumentVersionRead(BaseModel):
    """
    One version (one Generate) of a document, newest first in the list.

    - created_by_name: the user who generated it ("Deleted user" when gone)
    - pdf_status / pdf_error: the version's PDF conversion state
    - has_docx / has_pdf: the file can be downloaded (false once pruned)
    - files_pruned: retention removed the files (downloads answer 410)
    - changed_fields: field_names whose value differs from the previous
      version ([] for version 1)
    - docx_url / pdf_url: per-version download URLs, null when unavailable
    """

    version: int
    created_at: datetime
    created_by_name: str
    # V1.7 P2.1: "manual_edit" = the Word file of base_version edited by hand.
    source: VersionSource = "generated"
    base_version: int | None = None
    template_version: int | None
    pdf_status: PdfStatus | None
    pdf_error: str | None = None
    has_docx: bool
    has_pdf: bool
    files_pruned: bool
    changed_fields: list[str]
    is_latest: bool
    docx_url: str | None = None
    pdf_url: str | None = None


class DocumentVersionDetail(DocumentVersionRead):
    """A version with its values, shaped like the preview's sections (from the snapshot)."""

    document_id: int
    sections: list[PreviewSection]
