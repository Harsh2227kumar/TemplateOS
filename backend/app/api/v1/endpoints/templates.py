import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Form, File, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.services import docx_parser
from app.services.docx_cleaner import (
    apply_replacements_with_results,
    get_renderable_path,
)
from app.services.storage_service import (
    StorageError,
    StoredFileNotFoundError,
    storage_service,
)
from app.services.template_access import user_can_view_template
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
    delete_fields_by_template,
    get_fields_by_template,
)
from app.schemas.template import (
    TemplateCreate,
    TemplateResponse,
    TemplateListItem,
    TemplateLibraryResponse,
)
from app.schemas.template_field import (
    DetectionSummary,
    DetectionWarnings,
    DuplicateFieldWarning,
    InvalidFieldNameWarning,
    PlaceholderDetectionResponse,
    TemplateFieldCreate,
    TemplateFieldRead,
)
from app.schemas.cleaning import (
    CleanTemplateRequest,
    CleanTemplateResponse,
    CleanWarnings,
    ReplacementResult,
)
from app.models.template import Template
from app.models.template_field import TemplateField

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

    # 2. Read + empty check
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 3. File size check
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds the 10 MB limit")

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
            detail="Invalid category. Allowed: notice, mom, report, application, letter, certificate, proposal, invoice, custom",
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


@router.post(
    "/{template_id}/detect-placeholders",
    response_model=PlaceholderDetectionResponse,
)
async def detect_placeholders(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
    force: bool = Query(False, description="Replace existing fields with a fresh scan"),
) -> PlaceholderDetectionResponse:
    """
    Detect every {{placeholder}} in the template's original DOCX and persist
    the valid ones as ordered template_fields. Read-only on the DOCX.

    Owner-only. Idempotent: re-running without force returns the existing
    fields plus fresh warnings; force=true replaces the stored fields.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the template owner can detect placeholders"
        )

    if not template.original_file_path:
        raise HTTPException(status_code=409, detail="Template has no source file")

    logger.info(
        f"Placeholder detection started for template {template_id} (force={force})"
    )
    try:
        docx_bytes = await asyncio.to_thread(
            storage_service.read_bytes, template.original_file_path
        )
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=409, detail="Source file missing on disk"
        ) from None

    try:
        result = await asyncio.to_thread(docx_parser.detect_placeholders, docx_bytes)
    except Exception as e:
        logger.error(f"Placeholder detection failed for template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not parse the template document"
        ) from None

    existing_fields = get_fields_by_template(db, template_id)
    already_detected = bool(existing_fields) and not force

    if already_detected:
        # Do not duplicate: return the existing fields with fresh warnings.
        detected_fields = existing_fields
    else:
        if force:
            delete_fields_by_template(db, template_id)
        field_payloads = [
            TemplateFieldCreate(
                field_name=field.key,
                field_label=docx_parser.humanize_key(field.key),
                field_type="text",
                is_required=True,
                display_order=field.display_order,
            )
            for field in result.valid_fields
        ]
        detected_fields = bulk_create_fields(db, template_id, field_payloads)

        # Advance the status without ever downgrading field_configured/active.
        if template.status in ("uploaded", "placeholder_detected"):
            template.status = "placeholder_detected"
            db.commit()
            db.refresh(template)

    logger.info(
        f"Placeholder detection finished for template {template_id}: "
        f"{result.unique_valid} valid, {len(result.invalid_names)} invalid, "
        f"{len(result.duplicates)} duplicates (already_detected={already_detected})"
    )

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
    )


@router.get("/{template_id}/content")
async def get_template_content(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """
    Return the ORIGINAL DOCX's text segments (body, tables, headers, footers)
    so the owner can select sample text for cleaning. View-access protected.
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=403, detail="You do not have access to this template"
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

    return {
        "template_id": template_id,
        "segments": segments,
        "has_processed": template.processed_file_path is not None,
    }


@router.post("/{template_id}/clean", response_model=CleanTemplateResponse)
async def clean_template(
    template_id: int,
    request: CleanTemplateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CleanTemplateResponse:
    """
    Convert owner-confirmed sample text into {{placeholders}} in a NEW
    processed DOCX (templates/processed/). The original file is never
    modified. Owner-only, manual-confirmation required. Re-cleaning always
    regenerates from the ORIGINAL, so replacements never stack.
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
    try:
        original_bytes = await asyncio.to_thread(
            storage_service.read_bytes, template.original_file_path
        )
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=409, detail="Source file missing on disk"
        ) from None

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

    # Save the processed copy (separate file; original untouched).
    stored = await asyncio.to_thread(
        storage_service.save_bytes,
        "templates_processed",
        template.original_filename or "template.docx",
        processed_bytes,
    )
    template = set_processed_path(db, template, stored.path)

    # Upsert a field per MATCHED replacement (append_field skips duplicates).
    created_fields = []
    for replacement, result in zip(request.replacements, results):
        if not result.matched:
            continue
        field = append_field(
            db,
            template_id,
            TemplateFieldCreate(
                field_name=replacement.placeholder_key,
                field_label=replacement.field_label
                or docx_parser.humanize_key(replacement.placeholder_key),
                field_type=replacement.field_type or "text",
                example_value=replacement.sample_text,
                is_required=True,
                section=replacement.section,
                source="cleaned",
            ),
        )
        if field is not None:
            created_fields.append(field)

    # Status: field_configured when marked, else placeholder_detected —
    # advance_status is forward-only and never downgrades.
    target = "field_configured" if request.mark_configured else "placeholder_detected"
    template = advance_status(db, template, target)

    unmatched = [
        r.sample_text for r in results if not r.matched and r.reason != "invalid_key"
    ]
    invalid_keys = [r.placeholder_key for r in results if r.reason == "invalid_key"]
    logger.info(
        f"Cleaning finished for template {template_id}: "
        f"{len(created_fields)} field(s) created, "
        f"{len(unmatched)} unmatched, {len(invalid_keys)} invalid key(s)"
    )

    return CleanTemplateResponse(
        template_id=template_id,
        status=template.status,
        processed_file_path=stored.path,
        created_fields=created_fields,
        results=[
            ReplacementResult(
                placeholder_key=result.placeholder_key,
                sample_text=result.sample_text,
                occurrences=result.occurrences,
                matched=result.matched,
                reason=result.reason,
            )
            for result in results
        ],
        warnings=CleanWarnings(unmatched=unmatched, invalid_keys=invalid_keys),
    )
