"""
AI fill assistant schemas (V1.7 Phase 2.2 - Member 3).

Two groups:

1. What the MODEL returns (instructor response_model): AiFillTurn with
   AiFillProposalOut / AiFillQuestionOut. Lenient on purpose: over-long
   strings are cut and odd shapes are tolerated, because every reply goes
   through the deterministic post-processing of app.services.ai_fill_service
   before anything reaches the user.
2. The API contract (Prompts/V1.7-P2.2.md §5): requests, the stored chat,
   budgets and the fit report.

Proposals are PROPOSALS ONLY: nothing here writes document_values. The
frontend applies them to the form and saves through PUT /documents/{id}/values
with ai_action "ai_fill".
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings

Confidence = Literal["high", "medium", "low"]
Origin = Literal["empty", "ai", "user"]
Stage = Literal["asking", "filling", "ready"]
QuestionKind = Literal["missing", "unclear", "conflict", "more_detail"]

MAX_FORM_STATE_ITEMS = 500
MAX_FORM_STATE_VALUE_CHARS = 50_000
MAX_ANSWERS = 10
MAX_PROPOSAL_VALUE_CHARS = 20_000
MAX_PROPOSAL_ITEMS = 100


def _cut(value, limit: int):
    return value[:limit] if isinstance(value, str) else value


# --- Model output (instructor) ---


class AiFillProposalOut(BaseModel):
    """One proposed field value. `value` for text / textarea / date / number, `items` for list fields."""

    field_name: str = Field(..., description="The field key exactly as listed in FORM FIELDS")
    value: str | None = Field(default=None, description="Value for text, textarea, date (YYYY-MM-DD) and number fields")
    items: list[str] | None = Field(default=None, description="Items for list fields, one entry per item")
    source_text: str | None = Field(default=None, description="The user's own words this value comes from")
    confidence: Confidence = Field(
        default="medium",
        description="high = stated clearly; medium = incomplete or rewritten from little input; low = guessed or ambiguous",
    )
    reason: str | None = Field(default=None, description="Short reason for a medium / low confidence")

    @field_validator("value", mode="before")
    @classmethod
    def cut_value(cls, value):
        return _cut(value, MAX_PROPOSAL_VALUE_CHARS)

    @field_validator("items", mode="before")
    @classmethod
    def cut_items(cls, value):
        if isinstance(value, list):
            return [_cut(item, 2000) for item in value[:MAX_PROPOSAL_ITEMS] if isinstance(item, str)]
        return value

    @field_validator("source_text", mode="before")
    @classmethod
    def cut_source(cls, value):
        return _cut(value, 500)

    @field_validator("reason", mode="before")
    @classmethod
    def cut_reason(cls, value):
        return _cut(value, 300)


class AiFillQuestionOut(BaseModel):
    """One question to the user about one topic."""

    id: str | None = None
    text: str = Field(..., description="The question, one topic, plain language")
    field_names: list[str] = Field(default_factory=list, description="Field keys this question is about")
    choices: list[str] = Field(default_factory=list, description="Two to four likely answers, when there are any")
    kind: QuestionKind = Field(
        default="missing",
        description="missing = never mentioned; unclear = ambiguous or incomplete; conflict = two different answers; more_detail = a long text needs more facts",
    )

    @field_validator("text", mode="before")
    @classmethod
    def cut_text(cls, value):
        return _cut(value, 300)

    @field_validator("field_names", mode="before")
    @classmethod
    def cut_fields(cls, value):
        return value[:5] if isinstance(value, list) else value

    @field_validator("choices", mode="before")
    @classmethod
    def cut_choices(cls, value):
        if isinstance(value, list):
            return [_cut(choice, 120) for choice in value[:4] if isinstance(choice, str) and choice.strip()]
        return value


class AiFillTurn(BaseModel):
    """The model's reply for one chat turn (instructor response_model)."""

    message: str = Field(..., description="One or two short sentences to the user about what was filled and what is needed")
    stage: Stage = Field(
        default="filling",
        description="asking = more information is needed before filling; filling = filled what was possible; ready = nothing left to ask",
    )
    proposals: list[AiFillProposalOut] = Field(default_factory=list)
    questions: list[AiFillQuestionOut] = Field(default_factory=list)

    @field_validator("message", mode="before")
    @classmethod
    def cut_message(cls, value):
        return _cut(value, 1000)


# --- API: request ---


class FormStateItem(BaseModel):
    """
    One field of the form as the browser sees it now (saved or not). `value`
    is the plain value (lists: JSON array string, rich text: its plain text).
    origin "user" locks the field for the AI.
    """

    field_name: str = Field(..., min_length=1, max_length=100)
    value: str = Field(default="", max_length=MAX_FORM_STATE_VALUE_CHARS)
    origin: Origin = "empty"


class QuestionAnswer(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=40)
    # The clicked choice; null when the question is answered in the message text.
    choice: str | None = Field(default=None, max_length=200)


class AiFillMessageCreate(BaseModel):
    """POST /documents/{id}/ai-fill/messages body."""

    message: str = Field(default="")
    answers: list[QuestionAnswer] = Field(default_factory=list, max_length=MAX_ANSWERS)
    skipped: list[str] = Field(default_factory=list, max_length=MAX_ANSWERS)
    form_state: list[FormStateItem] = Field(default_factory=list, max_length=MAX_FORM_STATE_ITEMS)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        limit = settings.ai_fill_max_message_chars
        if len(value) > limit:
            raise ValueError(f"The message is too long (at most {limit} characters)")
        return value

    @model_validator(mode="after")
    def require_content(self) -> "AiFillMessageCreate":
        has_answer = any(answer.choice and answer.choice.strip() for answer in self.answers)
        if not self.message and not has_answer:
            raise ValueError("Write a message or pick an answer")
        return self


# --- API: stored chat ---


class AiFillProposalRead(BaseModel):
    field_name: str
    value: str | None = None
    items: list[str] | None = None
    source_text: str | None = None
    confidence: Confidence
    reason: str | None = None
    over_budget: bool = False


class AiFillQuestionRead(BaseModel):
    id: str
    text: str
    field_names: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    kind: QuestionKind = "missing"
    # 1 for a first question, 2+ when the field was asked about before.
    attempt: int = 1


class AiFillMessageRead(BaseModel):
    id: int
    turn: int
    role: Literal["user", "assistant"]
    content: str
    answers: list[QuestionAnswer] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    proposals: list[AiFillProposalRead] = Field(default_factory=list)
    questions: list[AiFillQuestionRead] = Field(default_factory=list)
    stage: Stage | None = None
    created_at: datetime


class AiFillSessionInfo(BaseModel):
    id: int
    status: Literal["active", "completed"]
    turn_count: int
    max_turns: int

    model_config = ConfigDict(from_attributes=True)


class FieldBudgetRead(BaseModel):
    field_name: str
    placement: str
    budget: int
    unit: Literal["chars", "items"]
    item_budget: int | None = None
    hard: bool = False

    model_config = ConfigDict(from_attributes=True)


class AiFillProgress(BaseModel):
    """Stage and required-field progress of the latest turn."""

    stage: Stage
    missing_required: list[str] = Field(default_factory=list)
    # Required fields the AI stopped asking about (ask limit / skipped).
    needs_user: list[str] = Field(default_factory=list)
    required_total: int = 0
    required_filled: int = 0
    done: bool = False


class AiFillSessionRead(BaseModel):
    """GET /documents/{id}/ai-fill."""

    session: AiFillSessionInfo | None = None
    messages: list[AiFillMessageRead] = Field(default_factory=list)
    open_questions: list[AiFillQuestionRead] = Field(default_factory=list)
    budgets: list[FieldBudgetRead] = Field(default_factory=list)


class AiFillTurnResponse(AiFillProgress):
    """POST /documents/{id}/ai-fill/messages."""

    session: AiFillSessionInfo
    user_message: AiFillMessageRead
    assistant_message: AiFillMessageRead


# --- Fit check ---


class FitLongField(BaseModel):
    field_name: str
    label: str
    length: int
    budget: int
    unit: Literal["chars", "items"]


class FitReport(BaseModel):
    """
    Does the generated version fit the template? `checked` false (with a
    reason) when there is no PDF to count pages of; budgets are still listed.
    """

    version: int | None = None
    pages: int | None = None
    baseline_pages: int | None = None
    overflow: bool = False
    long_fields: list[FitLongField] = Field(default_factory=list)
    checked: bool = False
    reason: str | None = None


class AiConfigRead(BaseModel):
    """GET /system/ai-config: what the UI may offer (no secrets)."""

    enabled: bool
    fill_enabled: bool
