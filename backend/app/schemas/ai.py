"""
AI suggestion schemas (V1.3 Phase 4 — Member 3).

Contracts:
- FieldSuggestion is the atomic unit Member 2's ai_service returns (via
  instructor's response_model) and Member 1 renders in the suggest-fields
  UI. Suggestions are PROPOSALS ONLY — nothing is persisted until the
  owner accepts one through the Phase 3 field endpoints (source="ai").
- FieldSuggestionList is the instructor response_model wrapper.
- SuggestFieldsResponse is the POST /templates/{id}/suggest-fields
  envelope (model + counts + suggestions; no fields are written).
- AiGenerationRead exposes lean audit rows if the UI shows an AI history.
- ImproveTextRequest / ImproveTextResponse (V1.5 Phase 1) are the
  POST /ai/improve-text contract: one field's text in, improved text out.

field_type validates against FIELD_TYPES imported from the model — a
single source of truth (no "dropdown"; the MVP set has "textarea"/"list").
"""

import re
from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.template_field import FIELD_TYPES

# Same rule as Phase 1's VALID_KEY_PATTERN (app/services/docx_parser.py),
# Phase 2's cleaning schema, and Phase 3's field editor schema.
_SUGGESTION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class FieldSuggestion(BaseModel):
    """
    One AI-proposed field.

    field_name follows the placeholder key rule (lowercase snake_case,
    starting with a letter) so an accepted suggestion maps 1:1 onto a
    template_field via the Phase 3 create/sync endpoints.
    """

    field_name: str = Field(..., max_length=100)
    field_label: str | None = Field(default=None, max_length=150)
    field_type: str = Field(default="text", max_length=20)
    section: str | None = Field(default=None, max_length=100)
    is_required: bool = True
    example_value: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(
        default=None,
        description="Why the AI suggests this field (shown in the UI)",
    )

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, value: str) -> str:
        if not _SUGGESTION_KEY_PATTERN.match(value):
            raise ValueError(
                "field_name must be lowercase snake_case "
                "(letters, digits, underscores) and start with a letter"
            )
        return value

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, value: str) -> str:
        if value not in FIELD_TYPES:
            raise ValueError(
                f"Unsupported field type: {value}. Allowed: {', '.join(FIELD_TYPES)}"
            )
        return value


class FieldSuggestionList(BaseModel):
    """instructor response_model wrapper: the Bedrock call returns this shape."""

    suggestions: list[FieldSuggestion] = Field(default_factory=list)


class SuggestFieldsResponse(BaseModel):
    """Envelope for POST /templates/{id}/suggest-fields. Persists NOTHING."""

    template_id: int
    model: str
    existing_count: int
    suggestion_count: int
    suggestions: list[FieldSuggestion] = Field(default_factory=list)


class AiGenerationRead(BaseModel):
    """One lean AI audit row (action metadata only — never prompt bodies)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action_type: str
    model: str
    template_id: int | None
    document_id: int | None
    field_key: str | None
    status: str
    suggestions_count: int | None
    created_at: datetime


# --- V1.5 Phase 1: basic AI writing actions on a single field ---

AiTextAction = Literal["grammar", "tone", "concise", "formal"]
AI_TEXT_ACTIONS: tuple[str, ...] = get_args(AiTextAction)

# Cap the text sent to the model per call (token/cost control).
MAX_IMPROVE_TEXT_CHARS = 5000


class ImproveTextRequest(BaseModel):
    """
    POST /ai/improve-text body. document_id is optional: the user may run an
    action on a new form before the draft has been saved for the first time.
    """

    template_id: int
    document_id: int | None = None
    field_name: str = Field(..., min_length=1, max_length=100)
    original_text: str = Field(..., min_length=1, max_length=MAX_IMPROVE_TEXT_CHARS)
    action_type: AiTextAction

    @field_validator("original_text")
    @classmethod
    def validate_original_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original_text must not be blank")
        return value


class ImproveTextResponse(BaseModel):
    """The improved text that replaces the field's value in the form."""

    improved_text: str
