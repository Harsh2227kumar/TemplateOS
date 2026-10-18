"""
V1.7 Phase 1 - Document preview schemas.

Response models of GET /api/v1/documents/{document_id}/preview (the
"check before you generate / download" page). Contract: Prompts/V1.7-P1.md §3.

Who fills what:
- document / template ........ endpoint, from get_document_for_preview()
- sections / completeness .... app.services.document_preview helpers
- generation / permissions ... endpoint (storage checks, URLs, owner rule)

Never put storage paths here: only basenames (pdf_filename) and API URLs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.document import AiAction, PdfStatus, ValueFormat


class PreviewDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class PreviewTemplate(BaseModel):
    id: int
    name: str
    category: str
    version: int
    has_processed_file: bool


class PreviewCompleteness(BaseModel):
    """Required fields only; missing_required lists field_names in display order."""

    required_total: int
    required_filled: int
    missing_required: list[str]


class PreviewField(BaseModel):
    """
    One template field as the generated document will show it.

    - value: raw saved value (list fields: the JSON-array string); None when
      the field was never saved
    - display_value: formatted exactly like generation ("" when empty)
    - items: list fields only, blank items dropped; None for other types
    - is_empty: same rule as the save validator
    - missing_required: is_required and is_empty
    - value_format / rich_content (V1.7 P2): "rich" textarea values carry the
      Tiptap JSON; value and display_value are its plain-text projection
    - ai_modified / ai_action: the saved value was written by AI
    """

    field_name: str
    label: str
    field_type: str
    is_required: bool
    ai_enabled: bool
    display_order: int
    value: str | None
    display_value: str
    items: list[str] | None
    is_empty: bool
    missing_required: bool
    value_format: ValueFormat = "plain"
    rich_content: dict[str, Any] | None = None
    ai_modified: bool = False
    ai_action: AiAction | None = None


class PreviewSection(BaseModel):
    name: str
    fields: list[PreviewField]


class PreviewGeneration(BaseModel):
    """Latest generated output; DocumentPreview.generation is None until the first generate."""

    generated_at: datetime
    is_stale: bool
    template_version: int | None
    docx_available: bool
    docx_url: str
    pdf_status: PdfStatus
    pdf_error: str | None
    pdf_available: bool
    pdf_url: str | None
    pdf_filename: str | None
    # V1.7 P2: the latest version's number and how many versions exist.
    version: int | None = None
    versions_count: int = 0


class PreviewPermissions(BaseModel):
    can_edit: bool
    can_generate: bool
    can_download: bool


class DocumentPreview(BaseModel):
    document: PreviewDocument
    template: PreviewTemplate
    completeness: PreviewCompleteness
    sections: list[PreviewSection]
    generation: PreviewGeneration | None
    permissions: PreviewPermissions
