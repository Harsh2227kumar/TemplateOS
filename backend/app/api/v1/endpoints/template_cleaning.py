"""
Cleaning routes: read a template's text content, suggest spots to turn
into placeholders, and preview / apply the replacements into a processed copy.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._template_common import (
    read_stored,
    record_file_revision,
    require_manage,
    save_processed,
)
from app.crud.template_crud import advance_status, get_template_by_id
from app.crud.template_field_crud import append_field, get_fields_by_template
from app.schemas.cleaning import (
    CleanAnchor,
    CleanPreviewResponse,
    CleanSuggestion,
    CleanSuggestionsResponse,
    CleanTemplateRequest,
    CleanTemplateResponse,
    CleanWarnings,
    ReplacementResult,
    SuggestionContext,
)
from app.schemas.template_field import TemplateFieldCreate, check_validation_rule
from app.services import docx_parser
from app.services.clean_suggester import HIGH_CONFIDENCE, suggest_cleaning
from app.services.docx_cleaner import (
    apply_replacements_with_results,
    check_renderable,
    get_renderable_path,
)
from app.services.field_inference import infer_field_meta
from app.services.template_access import user_can_view_template

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{template_id}/content")
def get_template_content(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
    source: str = Query(
        "original", pattern="^(original|processed)$",
        description="'processed' returns the cleaned copy (falls back to the original)",
    ),
) -> dict:
    """
    Return the DOCX's text segments (body, tables, text boxes, headers,
    footers) so the owner can select sample text for cleaning or review the
    cleaned result. View-access protected.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=403, detail="You do not have access to this template"
        )
    path = (
        get_renderable_path(template)
        if source == "processed"
        else template.original_file_path
    )
    if not path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = read_stored(path)

    try:
        segments = docx_parser.extract_text_segments(docx_bytes)
    except Exception as e:
        logger.error(f"Content extraction failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not read the template document"
        ) from None

    return {
        "template_id": template_id,
        "segments": segments,
        "has_processed": template.processed_file_path is not None,
        "source": "processed" if source == "processed" and template.processed_file_path else "original",
    }


@router.get(
    "/{template_id}/clean-suggestions",
    response_model=CleanSuggestionsResponse,
)
def get_clean_suggestions(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> CleanSuggestionsResponse:
    """
    Automatically find spots in the ORIGINAL DOCX that should become
    placeholders: empty labels ("Date:"), blank lines ("Name: ____"),
    empty/filled table cells, bracket hints ([Name]), filled label/value
    pairs, list blocks, and dates/emails/phones in running text. Each comes
    with a key, label, type, confidence and reason. Read-only; accepting a
    suggestion means sending it (with its `anchor`) to POST /clean.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    require_manage(template, current_user, "clean")
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = read_stored(template.original_file_path)
    try:
        report = suggest_cleaning(docx_bytes)
    except Exception as e:
        logger.error(f"Cleaning suggestions failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not analyze the template document"
        ) from None

    suggestions = [
        CleanSuggestion(
            id=item.id,
            kind=item.kind,
            group=item.group,
            placeholder_key=item.key,
            field_label=item.field_label,
            field_type=item.field_type,
            validation_rule=item.validation_rule,
            is_required=item.is_required,
            ai_enabled=item.ai_enabled,
            section=item.section,
            example_value=item.example_value,
            confidence=item.confidence,
            high_confidence=item.confidence >= HIGH_CONFIDENCE,
            reason=item.reason,
            sample_text=item.sample_text,
            location=item.location,
            shared_key_count=item.shared_with,
            anchor=CleanAnchor(
                paragraph_id=item.pid,
                start=item.start,
                end=item.end,
                action=item.action,
                paragraph_ids=item.paragraph_ids,
            ),
            context=SuggestionContext(
                before=item.context_before,
                match=item.sample_text,
                after=item.context_after,
                paragraph_text=item.paragraph_text,
            ),
        )
        for item in report.suggestions
    ]
    high = sum(1 for item in suggestions if item.high_confidence)
    logger.info(
        f"Cleaning suggestions for template {template_id}: "
        f"{len(suggestions)} suggestion(s), {high} high-confidence"
    )
    return CleanSuggestionsResponse(
        template_id=template_id,
        has_processed=template.processed_file_path is not None,
        suggestion_count=len(suggestions),
        high_confidence_count=high,
        high_confidence_threshold=HIGH_CONFIDENCE,
        existing_placeholders=report.existing_keys,
        suggestions=suggestions,
    )


def _clean_outcome(
    processed_bytes: bytes, results, existing_names: set[str] | None = None
) -> tuple[CleanWarnings, list[str], list[ReplacementResult]]:
    """Shared /clean + /clean-preview post-processing."""
    detection = docx_parser.detect_placeholders(processed_bytes)
    detected_keys = [field.key for field in detection.valid_fields]
    unmatched = [
        r.sample_text or r.placeholder_key
        for r in results
        if not r.matched and r.reason != "invalid_key"
    ]
    invalid_keys = [r.placeholder_key for r in results if r.reason == "invalid_key"]
    stale = sorted((existing_names or set()) - set(detected_keys))
    warnings = CleanWarnings(
        unmatched=unmatched,
        invalid_keys=invalid_keys,
        stale_fields=stale,
        render_error=check_renderable(processed_bytes),
    )
    result_models = [
        ReplacementResult(
            placeholder_key=result.placeholder_key,
            sample_text=result.sample_text,
            occurrences=result.occurrences,
            matched=result.matched,
            reason=result.reason,
        )
        for result in results
    ]
    return warnings, detected_keys, result_models




@router.post("/{template_id}/clean-preview", response_model=CleanPreviewResponse)
def preview_clean_template(
    template_id: int,
    request: CleanTemplateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CleanPreviewResponse:
    """
    Dry run of POST /clean: apply the replacements to a copy of the ORIGINAL
    and return the resulting text, per-replacement results and warnings.
    Nothing is saved and `confirm` is not required.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    require_manage(template, current_user, "clean")
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    original_bytes = read_stored(template.original_file_path)
    try:
        processed_bytes, results = apply_replacements_with_results(
            original_bytes, request.replacements
        )
        segments = docx_parser.extract_text_segments(processed_bytes)
        existing_names = {f.field_name for f in get_fields_by_template(db, template_id)}
        warnings, detected_keys, result_models = _clean_outcome(
            processed_bytes, results, existing_names
        )
    except Exception as e:
        logger.error(f"Clean preview failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not apply the requested replacements"
        ) from None

    return CleanPreviewResponse(
        template_id=template_id,
        segments=segments,
        results=result_models,
        warnings=warnings,
        detected_keys=detected_keys,
    )


@router.post("/{template_id}/clean", response_model=CleanTemplateResponse)
def clean_template(
    template_id: int,
    request: CleanTemplateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CleanTemplateResponse:
    """
    Convert owner-confirmed sample text / suggested spots into
    {{placeholders}} in a NEW processed DOCX (templates/processed/). The
    original file is never modified. Owner-only, manual-confirmation
    required. Re-cleaning always regenerates from the ORIGINAL, so
    replacements never stack.

    Each replacement is either a text replacement (sample_text, every
    occurrence) or an anchored one (from GET /clean-suggestions). A field is
    upserted per matched key with inferred metadata (label, type,
    validation, section, example value) unless the request provides it.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    require_manage(template, current_user, "clean")

    if not request.confirm:
        raise HTTPException(status_code=400, detail="Cleaning must be confirmed")

    if not request.replacements:
        raise HTTPException(
            status_code=400, detail="At least one replacement is required"
        )

    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    logger.info(
        f"Cleaning started for template {template_id}: "
        f"{len(request.replacements)} replacement(s) from user {current_user.id}"
    )

    # ALWAYS start from the original bytes (re-clean regenerates, never stacks).
    original_bytes = read_stored(template.original_file_path)

    try:
        processed_bytes, results = apply_replacements_with_results(
            original_bytes,
            request.replacements,
        )
    except Exception as e:
        logger.error(f"Cleaning failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not apply the requested replacements"
        ) from None

    processed_path = save_processed(db, template, processed_bytes)
    record_file_revision(db, template, processed_path, processed_bytes, "clean", current_user.id)
    template = get_template_by_id(db, template_id) or template

    # Upsert a field per MATCHED key (append_field skips existing keys).
    created_fields = []
    for replacement, result in zip(request.replacements, results):
        if not result.matched:
            continue
        payload = _field_from_replacement(replacement)
        field = append_field(db, template_id, payload)
        if field is not None:
            created_fields.append(field)

    # Status: field_configured when marked, else placeholder_detected —
    # advance_status is forward-only and never downgrades.
    target = "field_configured" if request.mark_configured else "placeholder_detected"
    template = advance_status(db, template, target)

    existing_names = {f.field_name for f in get_fields_by_template(db, template_id)}
    warnings, detected_keys, result_models = _clean_outcome(
        processed_bytes, results, existing_names
    )
    logger.info(
        f"Cleaning finished for template {template_id}: "
        f"{len(created_fields)} field(s) created, "
        f"{len(warnings.unmatched)} unmatched, {len(warnings.invalid_keys)} invalid key(s), "
        f"{len(warnings.stale_fields)} stale field(s)"
    )

    return CleanTemplateResponse(
        template_id=template_id,
        status=template.status,
        processed_file_path=processed_path,
        created_fields=created_fields,
        results=result_models,
        warnings=warnings,
        detected_keys=detected_keys,
    )


def _field_from_replacement(replacement) -> TemplateFieldCreate:
    """Field payload for one applied replacement: request values win, else inference."""
    anchor = replacement.anchor
    sample = replacement.sample_text or None
    if anchor is not None and anchor.action in ("insert", "list"):
        sample = None  # nothing was "filled" there (or it was a list block)
    example = replacement.example_value or sample
    if example and not any(ch.isalnum() for ch in example):
        # A replaced blank ("-------", "______") is a fill-in mark, not an example.
        example = None
    meta = infer_field_meta(
        replacement.placeholder_key,
        label=replacement.field_label,
        value=example,
        section=replacement.section,
        field_type=replacement.field_type
        or ("list" if anchor is not None and anchor.action == "list" else None),
    )
    try:
        rule = check_validation_rule(replacement.validation_rule)
    except ValueError:
        rule = None
    return TemplateFieldCreate(
        field_name=replacement.placeholder_key,
        field_label=(replacement.field_label or meta.field_label)[:150],
        field_type=meta.field_type,
        example_value=(example or None) and example[:255],
        is_required=(
            replacement.is_required
            if replacement.is_required is not None
            else meta.is_required
        ),
        ai_enabled=(
            replacement.ai_enabled
            if replacement.ai_enabled is not None
            else meta.ai_enabled
        ),
        validation_rule=rule or meta.validation_rule,
        description=replacement.description,
        section=meta.section,
        source="cleaned",
    )
