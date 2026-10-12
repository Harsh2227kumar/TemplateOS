import asyncio
import logging
import zipfile
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Form, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.services import ai_service, docx_parser
from app.services.ai_service import AiUnavailableError
from app.services.clean_suggester import HIGH_CONFIDENCE, suggest_cleaning
from app.services.docx_cleaner import (
    apply_replacements_with_results,
    check_renderable,
    fix_placeholder_tokens,
    get_renderable_path,
)
from app.services.field_inference import infer_field_meta
from app.services.storage_service import (
    StorageError,
    StoredFileNotFoundError,
    storage_service,
)
from app.services.template_access import user_can_view_template
from app.crud.ai_generation_crud import log_ai_generation
from app.crud.template_crud import (
    advance_status,
    create_template,
    get_templates_by_user,
    get_template_by_id,
    get_library_templates,
    set_processed_path,
)
from app.crud.template_field_crud import (
    append_field,
    bulk_create_fields,
    create_field,
    delete_field,
    delete_fields_by_template,
    field_exists,
    get_field_by_id,
    get_fields_by_template,
    move_field_to,
    reorder_fields,
    sync_fields,
    update_field,
)
from app.schemas.template import (
    TemplateCreate,
    TemplateResponse,
    TemplateListItem,
    TemplateLibraryResponse,
)
from app.schemas.ai import SuggestFieldsResponse
from app.schemas.template_field import (
    DetectionSummary,
    DetectionWarnings,
    DuplicateFieldWarning,
    FieldReorderRequest,
    FieldSyncRequest,
    InvalidFieldNameWarning,
    PlaceholderDetectionResponse,
    TemplateFieldCreate,
    TemplateFieldRead,
    TemplateFieldUpdate,
    VALIDATION_RULE_HELP,
    check_validation_rule,
)
from app.schemas.cleaning import (
    CleanAnchor,
    CleanPreviewResponse,
    CleanSuggestion,
    CleanSuggestionsResponse,
    CleanTemplateRequest,
    CleanTemplateResponse,
    CleanWarnings,
    FixPlaceholdersRequest,
    ReplacementResult,
    SuggestionContext,
)
from app.models.template import Template
from app.models.template_field import TemplateField
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "notice",
    "mom",
    "report",
    "application",
    "letter",
    "certificate",
    "proposal",
    "invoice",
    "custom",
}
ALLOWED_VISIBILITY = {"private", "public", "organization", "department", "group"}
ALLOWED_STATUSES = {
    "uploaded",
    "placeholder_detected",
    "field_configured",
    "active",
    "archived",
    "locked",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
# A DOCX is a zip; cap the total uncompressed size so a small "zip bomb"
# upload cannot exhaust memory when python-docx/docxtpl unpack it later.
MAX_UNCOMPRESSED_DOCX_BYTES = 100 * 1024 * 1024  # 100 MB


def _docx_content_error(content: bytes) -> str | None:
    """Return why `content` is not an acceptable DOCX, or None if it is."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, ValueError):
        return "File is not a valid DOCX document"
    if not any(entry.filename == "word/document.xml" for entry in entries):
        return "File is not a valid DOCX document"
    if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_DOCX_BYTES:
        return "DOCX content is too large"
    return None


def validate_filter_param(
    value: str | None, allowed: set[str], param_name: str
) -> None:
    """Validate a filter parameter against a set of allowed values."""
    if value is not None and value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}. Allowed: {', '.join(sorted(allowed))}",
        )


# --- GET endpoints ---
# IMPORTANT: /library must be declared BEFORE /{template_id}
# so FastAPI does not try to parse "library" as an integer.


@router.get("/library", response_model=TemplateLibraryResponse)
def list_library_templates(
    current_user: CurrentUser,
    db: DbSession,
    search: str | None = Query(
        None, max_length=100, description="Search by template name"
    ),
    category: str | None = Query(None, description="Filter by category"),
    visibility: str | None = Query(None, description="Filter by visibility"),
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> dict:
    """
    Return templates visible to the current user.
    Includes: user's own templates + public templates.
    Supports search, category filter, visibility filter, and pagination.
    """
    validate_filter_param(category, ALLOWED_CATEGORIES, "category")
    validate_filter_param(visibility, ALLOWED_VISIBILITY, "visibility")
    validate_filter_param(status, ALLOWED_STATUSES, "status")

    templates, total = get_library_templates(
        db=db,
        user_id=current_user.id,
        search=search,
        category=category,
        visibility=visibility,
        status=status,
        page=page,
        limit=limit,
    )

    return {
        "templates": templates,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/", response_model=list[TemplateListItem])
def list_my_templates(
    current_user: CurrentUser,
    db: DbSession,
) -> list[Template]:
    """Return all templates uploaded by the current user, newest first."""
    return get_templates_by_user(db, current_user.id)


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> Template:
    """Return a single template by ID. Accessible if user owns it OR it is public."""
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=403, detail="You do not have access to this template"
        )
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Permanently delete a template: the DB record (fields cascade) and every
    stored file (original + processed). Super-admin only — a destructive,
    irreversible action, so even the template owner cannot perform it.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=403, detail="Only a super admin can delete templates"
        )

    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    original_path = template.original_file_path
    processed_path = template.processed_file_path

    # DB first (fields cascade via ORM); file deletion is best-effort afterwards
    # so a storage hiccup can never leave a template row pointing at deleted files.
    db.delete(template)
    db.commit()

    for relative_path in (original_path, processed_path):
        if not relative_path:
            continue
        try:
            await asyncio.to_thread(storage_service.delete_file, relative_path)
        except StorageError:
            logger.warning(
                f"Template {template_id} deleted from DB but file could not be "
                f"removed from storage: {relative_path}"
            )

    logger.info(
        f"Super admin {current_user.id} deleted template {template_id} "
        f"(original={bool(original_path)}, processed={bool(processed_path)})"
    )


@router.get("/{template_id}/fields", response_model=list[TemplateFieldRead])
def get_template_fields(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> list[TemplateField]:
    """
    Return a template's detected fields, ordered by display_order.
    Reader access: anyone who can already view the template.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=403, detail="You do not have access to this template"
        )
    return get_fields_by_template(db, template_id)


# --- POST endpoints ---


@router.post(
    "/upload",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_template(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    category: str = Form(...),
    visibility: str = Form(...),
) -> Template:
    # Audited V1.2 Phase 2 — all validation, storage, and DB logic verified
    # 1. Validate file type
    filename = file.filename or "template.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX files are accepted")

    # 2. Read (bounded: never load more than the limit + 1 byte) + empty check
    content = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 3. File size check
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds the 10 MB limit")

    # 3b. Content check: the extension alone is client-controlled
    content_error = _docx_content_error(content)
    if content_error:
        raise HTTPException(status_code=400, detail=content_error)

    # 4. Validate name
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Template name is required")
    if len(clean_name) > 100:
        raise HTTPException(
            status_code=400, detail="Template name must be 100 characters or fewer"
        )

    # 5. Validate category
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Allowed: {', '.join(sorted(ALLOWED_CATEGORIES))}",
        )

    # 6. Validate visibility
    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    # 7. Save file via storage_service (in thread pool)
    try:
        logger.info(f"Saving template {filename} for user {current_user.id}")
        stored = await asyncio.to_thread(
            storage_service.save_bytes, "templates_original", filename, content
        )
    except StorageError as e:
        logger.error(f"Storage error while saving {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not save uploaded file",
        ) from None

    # 8. Insert DB record via create_template
    template_data = TemplateCreate(
        name=clean_name,
        description=description,
        category=category,
        visibility=visibility,
        original_file_path=stored.path,
        original_filename=filename,
        file_size_bytes=stored.size_bytes,
        file_extension=".docx",
        uploaded_by=current_user.id,
    )

    try:
        template = create_template(db, template_data)
        logger.info(f"Created template record {template.id} for user {current_user.id}")
    except Exception as e:
        logger.error(
            f"DB error while creating template record: {e}. Rolling back file."
        )
        await asyncio.to_thread(storage_service.delete_file, stored.path)
        raise HTTPException(
            status_code=500, detail="Could not save template record"
        ) from None

    return template


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


async def _read_stored(path: str) -> bytes:
    try:
        return await asyncio.to_thread(storage_service.read_bytes, path)
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=409, detail="Source file missing on disk"
        ) from None


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

    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can detect placeholders"
        )

    source_path = get_renderable_path(template)
    if not source_path:
        raise HTTPException(status_code=409, detail="Template has no source file")
    source_file = "processed" if template.processed_file_path else "original"

    logger.info(
        f"Placeholder detection started for template {template_id} "
        f"(force={force}, source={source_file})"
    )
    docx_bytes = await _read_stored(source_path)

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
    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can fix placeholders"
        )
    source_path = get_renderable_path(template)
    if not source_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = await _read_stored(source_path)
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

    await _save_processed(db, template, fixed_bytes)
    result = await asyncio.to_thread(docx_parser.detect_placeholders, fixed_bytes)
    response = _persist_detection(db, template, result, False, "processed")
    logger.info(
        f"Placeholder fix on template {template_id} by user {current_user.id}: "
        f"{sum(counts)} token(s) renamed"
    )
    return response


@router.get("/{template_id}/content")
async def get_template_content(
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

    docx_bytes = await _read_stored(path)

    try:
        segments = await asyncio.to_thread(
            docx_parser.extract_text_segments, docx_bytes
        )
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
async def get_clean_suggestions(
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
    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can clean this template"
        )
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    docx_bytes = await _read_stored(template.original_file_path)
    try:
        report = await asyncio.to_thread(suggest_cleaning, docx_bytes)
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


async def _save_processed(db: Session, template: Template, processed_bytes: bytes) -> str:
    """Store a new processed copy and drop the superseded one."""
    try:
        stored = await asyncio.to_thread(
            storage_service.save_bytes,
            "templates_processed",
            template.original_filename or "template.docx",
            processed_bytes,
        )
    except StorageError as e:
        logger.error(f"Storage error while saving processed template {template.id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not save the cleaned template"
        ) from None
    previous_processed_path = template.processed_file_path
    set_processed_path(db, template, stored.path)
    if previous_processed_path and previous_processed_path != stored.path:
        try:
            await asyncio.to_thread(storage_service.delete_file, previous_processed_path)
        except StorageError:
            logger.warning(
                f"Could not remove superseded processed file for template "
                f"{template.id}: {previous_processed_path}"
            )
    return stored.path


@router.post("/{template_id}/clean-preview", response_model=CleanPreviewResponse)
async def preview_clean_template(
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
    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can clean this template"
        )
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    original_bytes = await _read_stored(template.original_file_path)
    try:
        processed_bytes, results = await asyncio.to_thread(
            apply_replacements_with_results, original_bytes, request.replacements
        )
        segments = await asyncio.to_thread(
            docx_parser.extract_text_segments, processed_bytes
        )
        existing_names = {f.field_name for f in get_fields_by_template(db, template_id)}
        warnings, detected_keys, result_models = await asyncio.to_thread(
            _clean_outcome, processed_bytes, results, existing_names
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
async def clean_template(
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

    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can clean this template"
        )

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
    original_bytes = await _read_stored(template.original_file_path)

    try:
        processed_bytes, results = await asyncio.to_thread(
            apply_replacements_with_results,
            original_bytes,
            request.replacements,
        )
    except Exception as e:
        logger.error(f"Cleaning failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not apply the requested replacements"
        ) from None

    processed_path = await _save_processed(db, template, processed_bytes)
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
    warnings, detected_keys, result_models = await asyncio.to_thread(
        _clean_outcome, processed_bytes, results, existing_names
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
    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the template owner can request AI field suggestions",
        )
    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    try:
        docx_bytes = await asyncio.to_thread(
            storage_service.read_bytes, template.original_file_path
        )
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=409, detail="Source file missing on disk"
        ) from None

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


# --- V1.3 Phase 3: field editor (owner-only writes) ---
# ROUTE ORDERING: /{template_id}/fields/reorder is declared BEFORE the
# parameterized /{template_id}/fields/{field_id} so the static "reorder"
# suffix is never captured as a field_id. /library stays first in the file.


def _require_owner_editable(
    db: Session, template_id: int, current_user: User
) -> Template:
    """
    Load a template and enforce the guards shared by every field-editor
    write route: template exists (404), current user is the owner (403),
    and the template is not locked (403).
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can edit fields"
        )
    if template.status == "locked":
        raise HTTPException(
            status_code=403, detail="Template is locked and cannot be edited"
        )
    return template


_FIELD_NAME_RE = docx_parser.VALID_KEY_PATTERN


def _normalized_create_request(request: TemplateFieldCreate) -> TemplateFieldCreate:
    """
    Validate a single-field create the way the editor schemas do (key
    pattern, validation_rule grammar -> 422) and fill smart defaults for
    anything the client did not send (label, type, validation, AI flag).
    """
    name = request.field_name.strip()
    if not _FIELD_NAME_RE.match(name) or len(name) > 100:
        raise HTTPException(
            status_code=422,
            detail="field_name must be lowercase snake_case "
            "(letters, digits, underscores) and start with a letter",
        )
    try:
        rule = check_validation_rule(request.validation_rule)
    except ValueError:
        raise HTTPException(status_code=422, detail=VALIDATION_RULE_HELP) from None
    sent = request.model_fields_set
    meta = infer_field_meta(
        name,
        label=request.field_label,
        value=request.example_value,
        section=request.section,
        field_type=request.field_type if "field_type" in sent else None,
    )
    updates: dict = {"field_name": name, "validation_rule": rule}
    if not (request.field_label or "").strip():
        updates["field_label"] = meta.field_label
    if "field_type" not in sent:
        updates["field_type"] = meta.field_type
    if "validation_rule" not in sent:
        updates["validation_rule"] = meta.validation_rule
    if "ai_enabled" not in sent:
        updates["ai_enabled"] = meta.ai_enabled
    return request.model_copy(update=updates)


def _field_value_error(exc: ValueError) -> HTTPException:
    """Map a CRUD/model ValueError: duplicate field_name -> 409, else -> 422."""
    message = str(exc)
    if "already exists" in message:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


def _ensure_contiguous_order(db: Session, template_id: int) -> list[TemplateField]:
    """
    Renumber a template's fields to contiguous display_order 0..n-1 if an
    operation (e.g. a create with an explicit display_order) left gaps or
    duplicates. Relative order (display_order, id) is preserved.
    """
    fields = get_fields_by_template(db, template_id)
    if [field.display_order for field in fields] == list(range(len(fields))):
        return fields
    return reorder_fields(db, template_id, [field.id for field in fields])


@router.post(
    "/{template_id}/fields",
    response_model=TemplateFieldRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template_field(
    template_id: int,
    request: TemplateFieldCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> TemplateField:
    """
    Add one field to a template (field editor). Owner-only; locked templates
    reject writes. `display_order` defaults to the append position; an
    explicit value is honored and the set is renumbered to stay contiguous
    0..n-1. Duplicate field_name -> 409; invalid field_type -> 422.
    """
    _require_owner_editable(db, template_id, current_user)

    request = _normalized_create_request(request)

    if field_exists(db, template_id, request.field_name):
        raise HTTPException(
            status_code=409,
            detail=f"Field '{request.field_name}' already exists for this template",
        )

    explicit_position = (
        request.display_order if "display_order" in request.model_fields_set else None
    )
    try:
        field = create_field(
            db, template_id, request.model_copy(update={"display_order": 0})
        )
    except ValueError as exc:
        raise _field_value_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Field '{request.field_name}' already exists for this template",
        ) from None

    if explicit_position is not None:
        move_field_to(db, template_id, field.id, explicit_position)
        db.refresh(field)
    total = len(_ensure_contiguous_order(db, template_id))
    logger.info(
        f"Field '{field.field_name}' (id={field.id}) created on template "
        f"{template_id} by user {current_user.id} (total_fields={total})"
    )
    return field


@router.put("/{template_id}/fields/reorder", response_model=list[TemplateFieldRead])
def reorder_template_fields(
    template_id: int,
    request: FieldReorderRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> list[TemplateField]:
    """
    Reorder a template's fields. `ordered_ids` must be the full permutation
    of the template's current field ids, in the desired order — anything
    else (missing, extra, duplicated ids) -> 422. Owner-only; locked
    templates reject writes. Returns the fresh ordered field set.
    """
    _require_owner_editable(db, template_id, current_user)

    try:
        fields = reorder_fields(db, template_id, request.ordered_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    logger.info(
        f"Fields reordered on template {template_id} by user {current_user.id}: "
        f"{len(fields)} field(s)"
    )
    return fields


@router.patch("/{template_id}/fields/{field_id}", response_model=TemplateFieldRead)
def update_template_field(
    template_id: int,
    field_id: int,
    request: TemplateFieldUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TemplateField:
    """
    Partially update one field's metadata (label, type, required, help text,
    example, validation, section, AI flag, order) — only sent attributes are
    applied. Renaming to a key that exists on another field -> 409; invalid
    field_type -> 422. Owner-only; locked templates reject writes.
    """
    _require_owner_editable(db, template_id, current_user)

    field = get_field_by_id(db, field_id)
    if field is None or field.template_id != template_id:
        raise HTTPException(status_code=404, detail="Field not found on this template")

    if (
        request.field_name is not None
        and request.field_name != field.field_name
        and field_exists(db, template_id, request.field_name)
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Field '{request.field_name}' already exists for this template",
        )

    new_position = (
        request.display_order
        if "display_order" in request.model_fields_set and request.display_order is not None
        else None
    )
    changes = request.model_dump(exclude_unset=True, exclude={"display_order"})
    try:
        field = update_field(db, field, TemplateFieldUpdate(**changes))
        if new_position is not None:
            move_field_to(db, template_id, field.id, new_position)
            db.refresh(field)
    except ValueError as exc:
        raise _field_value_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Field '{request.field_name}' already exists for this template",
        ) from None

    logger.info(
        f"Field {field_id} ('{field.field_name}') updated on template "
        f"{template_id} by user {current_user.id}"
    )
    return field


@router.delete(
    "/{template_id}/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_template_field(
    template_id: int,
    field_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Remove one field. The template's remaining fields are reindexed to
    contiguous display_order 0..n-1 (no gaps, no duplicates). Owner-only;
    locked templates reject writes.
    """
    _require_owner_editable(db, template_id, current_user)

    field = get_field_by_id(db, field_id)
    if field is None or field.template_id != template_id:
        raise HTTPException(status_code=404, detail="Field not found on this template")

    field_name = field.field_name
    delete_field(db, field)
    remaining = len(get_fields_by_template(db, template_id))
    logger.info(
        f"Field '{field_name}' (id={field_id}) deleted from template {template_id} "
        f"by user {current_user.id} ({remaining} field(s) remain)"
    )


@router.put("/{template_id}/fields", response_model=list[TemplateFieldRead])
def sync_template_fields(
    template_id: int,
    request: FieldSyncRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> list[TemplateField]:
    """
    BULK SYNC — the field editor's "Save all" (full-sync semantics).

    `fields` is the COMPLETE desired state of the template's fields:
    - item with an id    -> update that field (only sent attributes applied)
    - item without an id -> create a new field (source defaults to 'manual')
    - existing fields ABSENT from the payload -> DELETED

    `display_order` is taken from array position (client values are ignored)
    and the save is all-or-nothing: a validation failure rolls everything
    back. Duplicate field_name in the payload -> 422; an id belonging to
    another template -> 422; a key conflict (e.g. two fields swapping names
    in one save) -> 409.

    With `mark_configured=true` (default) and at least one field saved, the
    template's status advances to `field_configured` (forward-only — a
    template already `active` is never downgraded). Returns the fresh,
    ordered field set.
    """
    template = _require_owner_editable(db, template_id, current_user)

    # Payload integrity: duplicate keys and foreign ids -> 422 before any write.
    seen_names: set[str] = set()
    for item in request.fields:
        if item.field_name in seen_names:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate field_name in payload: '{item.field_name}'",
            )
        seen_names.add(item.field_name)

    existing_ids = {field.id for field in get_fields_by_template(db, template_id)}
    for item in request.fields:
        if item.id is not None and item.id not in existing_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Field id {item.id} does not belong to template {template_id}",
            )

    try:
        fields = sync_fields(db, template_id, request.fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Field name conflict: this save would leave duplicate field "
            "keys (two fields cannot swap names in one save)",
        ) from None

    if request.mark_configured and fields:
        template = advance_status(db, template, "field_configured")

    kept_ids = {item.id for item in request.fields if item.id is not None}
    created_count = sum(1 for item in request.fields if item.id is None)
    logger.info(
        f"Field sync on template {template_id} by user {current_user.id}: "
        f"{created_count} created, {len(request.fields) - created_count} updated, "
        f"{len(existing_ids - kept_ids)} deleted -> {len(fields)} total "
        f"(status={template.status})"
    )
    return fields
