"""
Placeholder routes: detect {{placeholders}} in a template's fill-ready file
and one-click fix of malformed placeholder tokens.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._template_common import (
    read_stored,
    require_manage,
    save_processed,
)
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import (
    append_field,
    bulk_create_fields,
    delete_fields_by_template,
    get_fields_by_template,
)
from app.models.template import Template
from app.schemas.cleaning import FixPlaceholdersRequest
from app.schemas.template_field import (
    DetectionSummary,
    DetectionWarnings,
    DuplicateFieldWarning,
    InvalidFieldNameWarning,
    PlaceholderDetectionResponse,
    TemplateFieldCreate,
)
from app.services import docx_parser
from app.services.docx_cleaner import fix_placeholder_tokens, get_renderable_path
from app.services.field_inference import infer_field_meta

router = APIRouter()
logger = logging.getLogger(__name__)


def _field_create_from_detection(
    detected: docx_parser.DetectedField, example_value: str | None = None
) -> TemplateFieldCreate:
    """Detected placeholder -> field payload with inferred metadata."""
    meta = infer_field_meta(
        detected.key,
        value=None,
        section=detected.section,
        field_type="list" if detected.type_hint == "list" else None,
    )
    return TemplateFieldCreate(
        field_name=detected.key,
        field_label=meta.field_label,
        field_type=meta.field_type,
        is_required=meta.is_required,
        section=meta.section,
        validation_rule=meta.validation_rule,
        ai_enabled=meta.ai_enabled,
        example_value=example_value,
        display_order=detected.display_order,
    )

def _persist_detection(
    db: Session,
    template: Template,
    result: docx_parser.DetectionResult,
    force: bool,
    source_file: str,
) -> PlaceholderDetectionResponse:
    """
    Store a detection result as template_fields.

    - first run (no fields): create every detected key (inferred metadata)
    - re-run without force: ADD keys that are new in the document, keep every
      existing field and its configuration (already_detected = nothing new)
    - force: rebuild the field set from the document; example values of keys
      that survive are carried over
    Fields whose key is not in the document are reported as stale_fields.
    """
    template_id = template.id
    existing_fields = get_fields_by_template(db, template_id)
    existing_names = {field.field_name for field in existing_fields}
    added: list[str] = []

    if force:
        previous_examples = {
            field.field_name: field.example_value for field in existing_fields
        }
        delete_fields_by_template(db, template_id)
        payloads = [
            _field_create_from_detected_safe(field, previous_examples.get(field.key))
            for field in result.valid_fields
        ]
        bulk_create_fields(db, template_id, payloads)
        added = [field.key for field in result.valid_fields if field.key not in existing_names]
        already_detected = False
    elif existing_fields:
        for field in result.valid_fields:
            if field.key in existing_names:
                continue
            payload = _field_create_from_detected_safe(field)
            payload.display_order = 0  # append_field appends at the end
            if append_field(db, template_id, payload) is not None:
                added.append(field.key)
        already_detected = not added
    else:
        bulk_create_fields(
            db,
            template_id,
            [_field_create_from_detected_safe(field) for field in result.valid_fields],
        )
        added = [field.key for field in result.valid_fields]
        already_detected = False

    if not already_detected and template.status in ("uploaded", "placeholder_detected"):
        template.status = "placeholder_detected"
        db.commit()
        db.refresh(template)

    detected_fields = get_fields_by_template(db, template_id)
    detected_keys = {field.key for field in result.valid_fields}
    stale = [
        field.field_name
        for field in detected_fields
        if field.field_name not in detected_keys
    ]

    return PlaceholderDetectionResponse(
        template_id=template_id,
        status=template.status,
        already_detected=already_detected,
        detected_fields=detected_fields,
        warnings=DetectionWarnings(
            duplicates=[
                DuplicateFieldWarning(key=duplicate.key, count=duplicate.count)
                for duplicate in result.duplicates
            ],
            invalid_names=[
                InvalidFieldNameWarning(
                    raw=invalid.raw,
                    suggested_key=invalid.suggested_key,
                    count=invalid.count,
                    reason=invalid.reason,
                )
                for invalid in result.invalid_names
            ],
            parse_error=result.parse_warning,
        ),
        summary=DetectionSummary(
            total_matches=result.total_matches,
            unique_valid=result.unique_valid,
            invalid_count=len(result.invalid_names),
            duplicate_count=len(result.duplicates),
        ),
        source_file=source_file,
        added_fields=added,
        stale_fields=stale,
    )


def _field_create_from_detected_safe(
    detected: docx_parser.DetectedField, example_value: str | None = None
) -> TemplateFieldCreate:
    payload = _field_create_from_detection(detected, example_value)
    if payload.example_value and len(payload.example_value) > 255:
        payload.example_value = payload.example_value[:255]
    return payload

@router.post(
    "/{template_id}/detect-placeholders",
    response_model=PlaceholderDetectionResponse,
)
async def detect_placeholders(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
    force: bool = Query(False, description="Rebuild the field set from a fresh scan"),
) -> PlaceholderDetectionResponse:
    """
    Detect every {{placeholder}} in the template's FILL-READY file (the
    processed copy when cleaning produced one, else the original) and
    persist the valid ones as ordered template_fields with inferred metadata
    (label, type, validation, section). Read-only on the DOCX.

    Idempotent: without force, existing fields (and their configuration) are
    kept and only keys new to the document are added; force=true rebuilds
    the field set from the scan.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    require_manage(template, current_user, "detect placeholders in")

    source_path = get_renderable_path(template)
    if not source_path:
        raise HTTPException(status_code=409, detail="Template has no source file")
    source_file = "processed" if template.processed_file_path else "original"

    logger.info(
        f"Placeholder detection started for template {template_id} "
        f"(force={force}, source={source_file})"
    )
    docx_bytes = await read_stored(source_path)

    try:
        result = await asyncio.to_thread(docx_parser.detect_placeholders, docx_bytes)
    except Exception as e:
        logger.error(f"Placeholder detection failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not parse the template document"
        ) from None

    response = _persist_detection(db, template, result, force, source_file)
    logger.info(
        f"Placeholder detection finished for template {template_id}: "
        f"{result.unique_valid} valid, {len(result.invalid_names)} invalid, "
        f"{len(result.duplicates)} duplicates, {len(response.added_fields)} added, "
        f"{len(response.stale_fields)} stale (already_detected={response.already_detected})"
    )
    return response


@router.post(
    "/{template_id}/fix-placeholders",
    response_model=PlaceholderDetectionResponse,
)
async def fix_placeholders(
    template_id: int,
    request: FixPlaceholdersRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> PlaceholderDetectionResponse:
    """
    One-click fix for malformed placeholders: every {{ raw }} token (any
    spacing) in the fill-ready file becomes {{ key }}. The result is saved as
    the processed copy (the original is never modified), then detection
    re-runs without force so the fixed keys become fields.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    require_manage(template, current_user, "fix placeholders in")
    source_path = get_renderable_path(template)
    if not source_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = await read_stored(source_path)
    try:
        fixed_bytes, counts = await asyncio.to_thread(
            fix_placeholder_tokens,
            docx_bytes,
            [(fix.raw, fix.key) for fix in request.fixes],
        )
    except Exception as e:
        logger.error(f"Placeholder fix failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not update the template document"
        ) from None
    if not any(counts):
        raise HTTPException(
            status_code=422, detail="None of the placeholders to fix were found in the document"
        )

    await save_processed(db, template, fixed_bytes)
    result = await asyncio.to_thread(docx_parser.detect_placeholders, fixed_bytes)
    response = _persist_detection(db, template, result, False, "processed")
    logger.info(
        f"Placeholder fix on template {template_id} by user {current_user.id}: "
        f"{sum(counts)} token(s) renamed"
    )
    return response
