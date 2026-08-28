from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateFieldBase(BaseModel):
    field_name: str = Field(..., max_length=100)
    field_label: str | None = Field(default=None, max_length=150)
    field_type: str = Field(default="text", max_length=20)
    default_value: str | None = Field(default=None, max_length=255)
    is_required: bool = Field(default=True)
    description: str | None = Field(default=None)
    section: str | None = Field(default=None, max_length=100)
    example_value: str | None = Field(default=None, max_length=255)
    validation_rule: str | None = Field(default=None, max_length=255)
    ai_enabled: bool = Field(default=False)
    display_order: int = Field(default=0)


class TemplateFieldCreate(TemplateFieldBase):
    """Payload used by detection to bulk-create fields (template_id comes from the CRUD layer)."""

    pass


class TemplateFieldUpdate(BaseModel):
    """Partial update payload for the Phase 3 field editor."""

    field_name: str | None = Field(None, max_length=100)
    field_label: str | None = Field(None, max_length=150)
    field_type: str | None = Field(None, max_length=20)
    default_value: str | None = Field(None, max_length=255)
    is_required: bool | None = None
    description: str | None = None
    section: str | None = Field(None, max_length=100)
    example_value: str | None = Field(None, max_length=255)
    validation_rule: str | None = Field(None, max_length=255)
    ai_enabled: bool | None = None
    display_order: int | None = None


class TemplateFieldRead(TemplateFieldBase):
    id: int
    template_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- V1.3 Phase 1 placeholder detection response ---
# Mirrors Member 2's DetectionResult (app/services/docx_parser.py) and the
# Member 1 frontend types (frontend/src/lib/api.ts).


class DuplicateFieldWarning(BaseModel):
    """A valid key that appears more than once; collapsed into one field."""

    key: str
    count: int


class InvalidFieldNameWarning(BaseModel):
    """A malformed token like {{Bad Name}}; reported, never persisted."""

    raw: str
    suggested_key: str
    count: int
    reason: str


class DetectionWarnings(BaseModel):
    duplicates: list[DuplicateFieldWarning] = Field(default_factory=list)
    invalid_names: list[InvalidFieldNameWarning] = Field(default_factory=list)
    parse_error: str | None = None


class DetectionSummary(BaseModel):
    total_matches: int
    unique_valid: int
    invalid_count: int
    duplicate_count: int


class PlaceholderDetectionResponse(BaseModel):
    template_id: int
    status: str
    already_detected: bool
    detected_fields: list[TemplateFieldRead] = Field(default_factory=list)
    warnings: DetectionWarnings
    summary: DetectionSummary
