"""
AI route for templates: propose additional fields (Claude on Bedrock).
Proposals only; nothing is written to template_fields.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._template_common import read_stored, require_manage
from app.core.config import settings
from app.crud.ai_generation_crud import log_ai_generation
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import get_fields_by_template
from app.schemas.ai import SuggestFieldsResponse
from app.services import ai_service, docx_parser
from app.services.ai_service import AiUnavailableError

router = APIRouter()
logger = logging.getLogger(__name__)


# --- V1.3 Phase 4: AI field suggestions (owner-only, proposals only) ---


@router.post(
    "/{template_id}/suggest-fields",
    response_model=SuggestFieldsResponse,
)
async def suggest_template_fields(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> SuggestFieldsResponse:
    """
    Ask Claude Sonnet on AWS Bedrock (via instructor, validated output) to
    propose ADDITIONAL fields for this template based on its document text.

    Owner-only. Persists NOTHING to template_fields — suggestions are
    proposals the owner explicitly accepts through the Phase 3 field
    endpoints (source="ai"). Every attempt (success AND error) is logged to
    ai_generations. If AI is not configured or the provider fails, returns
    503 — the rest of the app keeps working without AI.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    require_manage(template, current_user, "request AI field suggestions for")
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = await read_stored(template.original_file_path)

    try:
        segments = await asyncio.to_thread(
            docx_parser.extract_text_segments, docx_bytes
        )
    except Exception as e:
        logger.error(f"Content extraction failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not read the template document"
        ) from None

    document_text = "\n".join(segment["text"] for segment in segments)
    existing_keys = [
        field.field_name for field in get_fields_by_template(db, template_id)
    ]

    logger.info(
        f"AI field suggestion started for template {template_id} "
        f"by user {current_user.id} (existing_fields={len(existing_keys)})"
    )
    try:
        suggestions = await asyncio.to_thread(
            ai_service.suggest_fields, document_text, existing_keys
        )
    except AiUnavailableError as e:
        log_ai_generation(
            db,
            action_type="suggest_fields",
            model=settings.bedrock_model_suggestions,
            template_id=template_id,
            created_by=current_user.id,
            status="error",
            suggestions_count=0,
            detail=str(e),
        )
        logger.warning(f"AI unavailable for template {template_id}: {e}")
        raise HTTPException(status_code=503, detail=str(e)) from None

    log_ai_generation(
        db,
        action_type="suggest_fields",
        model=settings.bedrock_model_suggestions,
        template_id=template_id,
        created_by=current_user.id,
        status="success",
        suggestions_count=len(suggestions),
    )
    logger.info(
        f"AI field suggestion finished for template {template_id}: "
        f"{len(suggestions)} suggestion(s) (nothing persisted)"
    )

    return SuggestFieldsResponse(
        template_id=template_id,
        model=settings.bedrock_model_suggestions,
        existing_count=len(existing_keys),
        suggestion_count=len(suggestions),
        suggestions=suggestions,
    )
