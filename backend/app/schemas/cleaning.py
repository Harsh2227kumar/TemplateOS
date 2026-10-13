"""
Template cleaning request/response schemas (V1.3 Phase 2 — Member 3).

Manual Template Cleaning lets an owner convert selected sample text in the
original DOCX into {{placeholders}}, producing a processed DOCX (Member 2's
docx_cleaner) while preserving the original. These are the data contracts
Member 2's GET /{id}/content + POST /{id}/clean endpoints consume/return and
Member 1's UI mirrors.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.template_field import FIELD_TYPES
from app.schemas.template_field import TemplateFieldRead

# Same rule as Phase 1's VALID_KEY_PATTERN (app/services/docx_parser.py).
PLACEHOLDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class CleanAnchor(BaseModel):
    """
    Exact spot from GET /clean-suggestions (extension of the V1.3 contract).

    paragraph_id is the suggestion's paragraph (canonical walker order over
    the ORIGINAL file); start/end are character offsets in that paragraph.
    - replace: text[start:end] (must equal sample_text when one is sent)
    - insert:  {{ key }} goes in at `start` (empty values, empty table cells)
    - list:    paragraph_ids become {%p for item in key %}{{ item }}{%p endfor %}
    """

    paragraph_id: int = Field(..., ge=0)
    start: int = Field(default=0, ge=0)
    end: int = Field(default=0, ge=0)
    action: Literal["replace", "insert", "list"] = "replace"
    paragraph_ids: list[int] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def check_offsets(self) -> "CleanAnchor":
        if self.end < self.start:
            raise ValueError("anchor.end must be >= anchor.start")
        if self.action == "replace" and self.end == self.start:
            raise ValueError("a replace anchor needs end > start")
        if self.action == "list" and not self.paragraph_ids:
            self.paragraph_ids = [self.paragraph_id]
        return self


class PlaceholderReplacement(BaseModel):
    """One confirmed sample-text -> placeholder conversion from the owner."""

    sample_text: str = Field(
        default="",
        description="The exact text the owner selected (may be empty for an anchored insert)",
    )
    anchor: CleanAnchor | None = Field(
        default=None,
        description="Optional exact location (from /clean-suggestions); without it "
        "every occurrence of sample_text is replaced",
    )
    placeholder_key: str = Field(
        ..., description="Target placeholder key, lowercase snake_case"
    )
    field_label: str | None = Field(default=None, max_length=150)
    field_type: str | None = Field(
        default=None, description=f"One of {FIELD_TYPES} if provided"
    )
    section: str | None = Field(default=None, max_length=100)
    segment_index: int | None = Field(
        default=None,
        description="Optional scope hint (TextSegment.index) from the UI",
    )
    example_value: str | None = Field(default=None, max_length=255)
    validation_rule: str | None = Field(default=None, max_length=255)
    is_required: bool | None = None
    ai_enabled: bool | None = None
    description: str | None = None

    @model_validator(mode="after")
    def require_target(self) -> "PlaceholderReplacement":
        if self.anchor is None and not self.sample_text:
            raise ValueError("sample_text is required unless an anchor is given")
        return self

    @field_validator("placeholder_key")
    @classmethod
    def validate_placeholder_key(cls, value: str) -> str:
        if not PLACEHOLDER_KEY_PATTERN.match(value):
            raise ValueError(
                "placeholder_key must be lowercase snake_case "
                "(letters, digits, underscores) and start with a letter"
            )
        return value

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, value: str | None) -> str | None:
        if value is not None and value not in FIELD_TYPES:
            raise ValueError(
                f"Unsupported field type: {value}. Allowed: {', '.join(FIELD_TYPES)}"
            )
        return value


class CleanTemplateRequest(BaseModel):
    """Owner-confirmed batch of replacements to apply to the original DOCX."""

    replacements: list[PlaceholderReplacement] = Field(..., min_length=1)
    confirm: bool = Field(
        default=False,
        description="Must be true — cleaning is a manual-confirmation action",
    )
    mark_configured: bool = Field(
        default=False,
        description="If true, status advances to field_configured; else placeholder_detected",
    )


class ReplacementResult(BaseModel):
    """Per-replacement outcome, echoed to the UI."""

    placeholder_key: str
    sample_text: str
    occurrences: int = 0
    matched: bool = False
    reason: str | None = None


class CleanWarnings(BaseModel):
    unmatched: list[str] = Field(
        default_factory=list, description="Sample texts not found in the document"
    )
    invalid_keys: list[str] = Field(
        default_factory=list, description="Keys rejected by validation"
    )
    stale_fields: list[str] = Field(
        default_factory=list,
        description="Existing fields whose placeholder is no longer in the processed file",
    )
    render_error: str | None = Field(
        default=None,
        description="Set when docxtpl cannot parse the processed file (it would not render)",
    )


class CleanTemplateResponse(BaseModel):
    template_id: int
    status: str
    processed_file_path: str
    created_fields: list[TemplateFieldRead] = Field(default_factory=list)
    results: list[ReplacementResult] = Field(default_factory=list)
    warnings: CleanWarnings
    detected_keys: list[str] = Field(
        default_factory=list,
        description="Placeholder keys present in the processed file, in document order",
    )


class CleanPreviewSegment(BaseModel):
    index: int
    location: str
    text: str


class CleanPreviewResponse(BaseModel):
    """POST /clean-preview: what /clean would produce. Nothing is saved."""

    template_id: int
    segments: list[CleanPreviewSegment] = Field(default_factory=list)
    results: list[ReplacementResult] = Field(default_factory=list)
    warnings: CleanWarnings
    detected_keys: list[str] = Field(default_factory=list)


# --- Automatic cleaning suggestions (GET /{id}/clean-suggestions) ---

SuggestionGroup = Literal[
    "fixes",
    "lists",
    "tables",
    "blanks",
    "brackets",
    "empty_values",
    "filled_values",
    "detected_values",
]


class SuggestionContext(BaseModel):
    before: str = ""
    match: str = ""
    after: str = ""
    paragraph_text: str = ""


class CleanSuggestion(BaseModel):
    """One proposed placeholder. Accepting it = sending it back to /clean."""

    id: str = Field(..., description="Stable id: '<paragraph_id>:<start>:<end>:<kind>'")
    kind: str
    group: SuggestionGroup
    placeholder_key: str
    field_label: str
    field_type: str
    validation_rule: str | None = None
    is_required: bool = True
    ai_enabled: bool = False
    section: str | None = None
    example_value: str | None = None
    confidence: float = Field(..., ge=0, le=1)
    high_confidence: bool
    reason: str
    sample_text: str
    location: str
    shared_key_count: int = Field(
        default=1, description="How many suggestions share this key (one field fills them all)"
    )
    anchor: CleanAnchor
    context: SuggestionContext


class CleanSuggestionsResponse(BaseModel):
    template_id: int
    source: Literal["original"] = "original"
    has_processed: bool
    suggestion_count: int
    high_confidence_count: int
    high_confidence_threshold: float
    existing_placeholders: list[str] = Field(default_factory=list)
    suggestions: list[CleanSuggestion] = Field(default_factory=list)


class PlaceholderFix(BaseModel):
    """Rename one malformed token: every {{ raw }} becomes {{ key }}."""

    raw: str = Field(..., min_length=1, max_length=200)
    key: str

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not PLACEHOLDER_KEY_PATTERN.match(value):
            raise ValueError(
                "key must be lowercase snake_case "
                "(letters, digits, underscores) and start with a letter"
            )
        return value


class FixPlaceholdersRequest(BaseModel):
    fixes: list[PlaceholderFix] = Field(..., min_length=1, max_length=200)
