"""
AI endpoints for V1.5 Phase 1 — Basic AI Actions.

Endpoints:
- POST /ai/improve-text — rewrite ONE form field's text (grammar, tone,
  concise, formal, expand) with Amazon Nova on Bedrock and return the
  improved text. List fields are rewritten item by item (same item count).

Rules:
- Backend-only AI: only FastAPI calls Bedrock.
- Nothing is persisted except one lean ai_generations audit row per call
  (success AND error). The improved text is returned to the form; the user
  saves it through the normal draft endpoints.
- Graceful degradation: AI not configured / provider failure -> 503; the
  rest of the app keeps working.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.crud.ai_generation_crud import log_ai_generation
from app.crud.document_crud import get_document_by_id
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import get_fields_by_template
from app.schemas.ai import ImproveTextRequest, ImproveTextResponse
from app.services import ai_service
from app.services.ai_service import AiUnavailableError
from app.services.template_access import user_can_view_template

router = APIRouter()
logger = logging.getLogger(__name__)

# Field types the text actions apply to (dates/numbers/emails are not prose).
AI_TEXT_FIELD_TYPES = ("text", "textarea", "list")


@router.post(
    "/improve-text", response_model=ImproveTextResponse, response_model_exclude_none=True
)
def improve_text(
    payload: ImproveTextRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ImproveTextResponse:
    """
    Improve one field's text with an AI action.

    - 404 if the template or document does not exist, or the field is not
      part of the template
    - 403 if the user cannot view the template or does not own the document
    - 422 if the field is not an AI-enabled text/textarea/list field, the
      value is sent in the wrong shape (original_items for a list field,
      original_text otherwise), or the document belongs to another template
    - 503 if AI is not configured or Bedrock fails (logged as status="error")
    """
    template = get_template_by_id(db, payload.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this template",
        )

    if payload.document_id is not None:
        document = get_document_by_id(db, payload.document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        if document.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this document",
            )
        if document.template_id != template.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Document does not belong to this template",
            )

    field = next(
        (
            f
            for f in get_fields_by_template(db, template.id)
            if f.field_name == payload.field_name
        ),
        None,
    )
    if field is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found in template",
        )
    if not field.ai_enabled or field.field_type not in AI_TEXT_FIELD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI actions are not enabled for this field",
        )

    is_list = field.field_type == "list"
    if is_list != (payload.original_items is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Send original_items (one entry per item) for a list field"
                if is_list
                else "Send original_text for a text or paragraph field"
            ),
        )

    model = ai_service.model_for_action(payload.action_type)
    chars = (
        sum(len(item) for item in payload.original_items)
        if is_list
        else len(payload.original_text)
    )
    logger.info(
        f"AI improve-text started: action={payload.action_type} "
        f"template={template.id} document={payload.document_id} "
        f"field={payload.field_name} user={current_user.id} "
        f"chars={chars}" + (f" items={len(payload.original_items)}" if is_list else "")
    )
    try:
        if is_list:
            improved_items = ai_service.improve_items(
                payload.action_type, payload.original_items
            )
            improved = "\n".join(improved_items)
        else:
            improved_items = None
            improved = ai_service.improve_text(payload.action_type, payload.original_text)
    except AiUnavailableError as e:
        log_ai_generation(
            db,
            action_type=payload.action_type,
            model=model or "unconfigured",
            template_id=template.id,
            document_id=payload.document_id,
            created_by=current_user.id,
            field_key=payload.field_name,
            status="error",
            detail=str(e),
        )
        logger.warning(
            f"AI improve-text unavailable for template {template.id} "
            f"field {payload.field_name}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from None

    log_ai_generation(
        db,
        action_type=payload.action_type,
        model=model,
        template_id=template.id,
        document_id=payload.document_id,
        created_by=current_user.id,
        field_key=payload.field_name,
        status="success",
    )
    logger.info(
        f"AI improve-text finished: action={payload.action_type} "
        f"template={template.id} field={payload.field_name} "
        f"user={current_user.id} chars_out={len(improved)}"
    )
    return ImproveTextResponse(improved_text=improved, improved_items=improved_items)
