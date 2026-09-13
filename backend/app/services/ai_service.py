"""
AI suggestion service (V1.3 Phase 4 — Member 2).

The FIRST TemplateOS AI feature: propose missing template fields from a
document's text using AWS Bedrock (Claude Sonnet) via the Anthropic SDK,
wrapped with instructor so the model's reply comes back as a VALIDATED
Pydantic object (FieldSuggestionList) — never hand-parsed JSON.

Rules (MD/features.md §10):
- Backend-only AI. The frontend calls FastAPI; only FastAPI calls Bedrock.
- Suggestions are PROPOSALS ONLY — this module never touches the database;
  the owner accepts them through the Phase 3 field endpoints (source="ai").
- Graceful degradation: anything missing (deps, region, credentials) or any
  provider failure raises AiUnavailableError, which the endpoint maps to
  503. The rest of the app keeps working without AI.

Import safety: anthropic/instructor are imported INSIDE _build_client, so
importing this module (and booting the app, and running non-AI tests) works
even when the AI dependencies are not installed.
"""

import logging

from app.core.config import settings
from app.schemas.ai import FieldSuggestion, FieldSuggestionList
from app.services.docx_parser import VALID_KEY_PATTERN

logger = logging.getLogger(__name__)

# Cap the document excerpt fed to the model (token/cost control).
MAX_DOCUMENT_TEXT_CHARS = 6000

_SYSTEM_PROMPT = (
    "You help turn a document into a reusable template. Given the document "
    "text and the placeholders that already exist, suggest ADDITIONAL fields "
    "that should be captured. Prefer lowercase snake_case keys, meaningful "
    "labels, correct MVP types (text, textarea, date, number, list, "
    "signature), a sensible section, whether it is required, and an example "
    "value. Do NOT repeat existing keys. If the document already covers "
    "everything, return an empty list."
)


class AiUnavailableError(Exception):
    """AI (Bedrock) is not configured or the provider call failed."""


def _build_client():
    """
    Return an instructor-wrapped AnthropicBedrock client, or raise
    AiUnavailableError. Every failure mode (missing deps, missing region,
    unresolvable credentials, SDK construction error) funnels into
    AiUnavailableError so FastAPI never sees a raw 500.
    """
    if not settings.ai_is_configured:
        raise AiUnavailableError(
            "AI is not configured (missing AWS region or credentials)"
        )
    try:
        import instructor
        from anthropic import AnthropicBedrock
    except ImportError as exc:
        raise AiUnavailableError(
            "AI dependencies are not installed (anthropic/instructor)"
        ) from exc
    try:
        return instructor.from_anthropic(
            AnthropicBedrock(aws_region=settings.aws_region)
        )
    except Exception as exc:
        logger.error(f"Could not initialize the Bedrock AI client: {exc}")
        raise AiUnavailableError("AI is currently unavailable") from exc


def suggest_fields(
    document_text: str, existing_keys: list[str]
) -> list[FieldSuggestion]:
    """
    Ask Claude Sonnet on Bedrock for ADDITIONAL template fields and return
    the validated, deduplicated suggestions. Provider/dependency failures
    raise AiUnavailableError (the endpoint maps that to 503).
    """
    client = _build_client()

    existing = list(existing_keys)
    excerpt = document_text[:MAX_DOCUMENT_TEXT_CHARS]
    user_content = (
        "Existing placeholder keys (do NOT suggest these again):\n"
        f"{', '.join(existing) if existing else '(none)'}\n\n"
        "Document text:\n"
        f"{excerpt}"
    )

    try:
        result = client.messages.create(
            model=settings.bedrock_model_suggestions,
            max_tokens=settings.ai_max_output_tokens,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_content},
            ],
            response_model=FieldSuggestionList,
        )
    except AiUnavailableError:
        raise
    except Exception as exc:
        logger.error(f"AI field suggestion call failed: {exc}")
        raise AiUnavailableError("AI is currently unavailable") from exc

    # instructor already validated the schema; still enforce the key rule
    # and dedupe against existing keys (and within the model's own reply).
    taken = set(existing)
    cleaned: list[FieldSuggestion] = []
    for suggestion in result.suggestions:
        if (
            not VALID_KEY_PATTERN.match(suggestion.field_name)
            or suggestion.field_name in taken
        ):
            continue
        taken.add(suggestion.field_name)
        cleaned.append(suggestion)
    return cleaned
