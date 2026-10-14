"""
V1.4 Phase 2 - Document Schemas

Pydantic schemas for document persistence (draft save functionality).
Used by the document endpoints (app/api/v1/endpoints/documents.py):
- POST /documents/create
- PUT /documents/{id}/values
- GET /documents
- GET /documents/{id}
- GET /documents/{id}/values
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Request-size bounds for PUT /documents/{id}/values (no prior limit existed).
MAX_DOCUMENT_VALUE_LENGTH = 50_000
MAX_VALUES_PER_REQUEST = 500

PdfStatus = Literal["ok", "failed", "not_configured"]


# --- Generation (V1.6) ---


class GeneratedInfo(BaseModel):
    """
    Latest generated output of a document (null in DocumentRead / list items
    until the first POST /documents/{id}/generate).

    - pdf_status: ok (PDF available), failed (conversion failed, see
      pdf_error; retry with POST /generate-pdf), not_configured (no PDF
      converter on the server)
    - is_stale: the draft's values were saved after this generation
    """

    generated_at: datetime
    pdf_status: PdfStatus
    pdf_error: str | None = None
    docx_url: str
    pdf_url: str | None = None
    is_stale: bool = False
    template_version: int | None = None


class GenerateDocumentResponse(GeneratedInfo):
    """Response for POST /documents/{id}/generate and /generate-pdf."""

    document_id: int
    document_status: str


# --- Document Schemas ---


class DocumentCreate(BaseModel):
    """
    Payload for POST /documents/create.

    Creates a new document draft based on a template.
    Initial status is always 'draft'.
    """

    template_id: int = Field(..., description="ID of the template to create document from")
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional user-given name (auto-generated if null)",
    )


class DocumentUpdate(BaseModel):
    """
    Payload for PATCH /documents/{id}.

    Updates document metadata (name, status).
    All fields are optional for partial updates.
    """

    name: str | None = Field(default=None, max_length=255)
    status: str | None = Field(
        default=None,
        description=(
            "Status: draft, generated, submitted, approved, rejected, final. "
            "Phase 2 only uses 'draft' and 'generated'."
        ),
    )


class DocumentRead(BaseModel):
    """
    Response for POST /documents/create and GET /documents/{id}.

    Includes document metadata and the joined values (empty on create).
    """

    id: int
    template_id: int
    created_by: int
    name: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    # Optional: eagerly loaded values (when include_values=true)
    values: list["DocumentValueRead"] = Field(default_factory=list)
    # V1.6: latest generated output, null until generated
    generated: GeneratedInfo | None = None

    model_config = ConfigDict(from_attributes=True)


# --- DocumentValue Schemas ---


class DocumentValueCreate(BaseModel):
    """
    Payload for one field value in PUT /documents/{id}/values.

    The endpoint accepts a list of these for bulk upsert.
    """

    field_name: str = Field(
        ...,
        max_length=100,
        description="Must match template_fields.field_name",
    )
    value: str = Field(
        ...,
        max_length=MAX_DOCUMENT_VALUE_LENGTH,
        description=(
            "Value as string. For list fields, use JSON array string "
            "(e.g., '[\"item1\", \"item2\"]'). For date, use ISO format "
            "(e.g., '2026-09-13'). For number, use string representation (e.g., '42')."
        ),
    )


class DocumentValueUpdate(BaseModel):
    """
    Payload for updating a single document value (future use).

    Phase 2 uses bulk upsert via DocumentValueCreate list.
    This schema is for potential future single-field update endpoint.
    """

    value: str = Field(..., description="New value as string")


class DocumentValueRead(BaseModel):
    """
    Response for document values in GET /documents/{id}/values or nested in DocumentRead.

    Returns the persisted value with metadata.
    """

    id: int
    document_id: int
    field_name: str
    value: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Bulk Operations ---


class DocumentValuesBulkUpsert(BaseModel):
    """
    Payload for PUT /documents/{id}/values (Phase 2).

    Accepts a list of field values for bulk upsert.
    Upsert behavior:
    - If (document_id, field_name) exists, update value + updated_at
    - If not, insert new row
    """

    values: list[DocumentValueCreate] = Field(
        ...,
        description="List of field values to upsert",
        min_length=1,
        max_length=MAX_VALUES_PER_REQUEST,
    )


class DocumentValuesBulkRead(BaseModel):
    """
    Response for PUT /documents/{id}/values and GET /documents/{id}/values.

    Shape: {document_id, values: list[DocumentValueRead]}. PUT returns the
    rows it upserted; GET returns all saved values (no specific order).
    """

    document_id: int
    values: list[DocumentValueRead]


# --- Validation Error Schemas (Phase 2) ---


class FieldValidationError(BaseModel):
    """
    One field validation error in the PUT /documents/{id}/values 422 response.

    Matches the dicts raised by app.services.document_validator, e.g.
    {"field_name": "email", "error": "Must be a valid email address"}.
    """

    field_name: str | None
    error: str


class DocumentValidationErrorResponse(BaseModel):
    """
    HTTP 422 response when document_values validation fails.

    {"detail": [{field_name, error}, ...]}. Note: request-body errors caught
    by Pydantic itself (e.g. an empty values list) use FastAPI's default
    {loc, msg, type} shape instead.
    """

    detail: list[FieldValidationError]


# --- Summary/List Schemas ---


class DocumentListItem(BaseModel):
    """
    Lightweight document item for GET /documents list view (Phase 2).

    Does not include values (use DocumentRead with include_values for that).
    """

    id: int
    template_id: int
    template_name: str  # Joined from templates.name
    name: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    generated: GeneratedInfo | None = None  # V1.6

    model_config = ConfigDict(from_attributes=True)


# --- Endpoint Mapping ---

"""

POST /documents/create
  Request: DocumentCreate
  Response: DocumentRead (empty values list)

PUT /documents/{id}/values
  Request: DocumentValuesBulkUpsert
  Response: DocumentValuesBulkRead
  Error: DocumentValidationErrorResponse (HTTP 422)

GET /documents
  Response: list[DocumentListItem] (user's drafts, ordered by updated_at desc)

GET /documents/{id}
  Response: DocumentRead (with values)

GET /documents/{id}/values
  Response: DocumentValuesBulkRead

Not yet implemented (schemas reserved for later phases):
PATCH /documents/{id}         Request: DocumentUpdate, Response: DocumentRead
DELETE /documents/{id}        (cascade deletes values via FK)
"""
