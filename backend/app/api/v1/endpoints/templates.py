import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Form, File, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.services.storage_service import StorageError, storage_service
from app.crud.template_crud import (
    create_template,
    get_templates_by_user,
    get_template_by_id,
    get_library_templates,
)
from app.schemas.template import (
    TemplateCreate,
    TemplateResponse,
    TemplateListItem,
    TemplateLibraryResponse,
)
from app.models.template import Template

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "notice", "mom", "report", "application",
    "letter", "certificate", "proposal", "invoice", "custom",
}
ALLOWED_VISIBILITY = {"private", "public", "organization", "department", "group"}
ALLOWED_STATUSES = {
    "uploaded", "placeholder_detected", "field_configured",
    "active", "archived", "locked",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_filter_param(value: str | None, allowed: set[str], param_name: str) -> None:
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
    search: str | None = Query(None, max_length=100, description="Search by template name"),
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
    if template.uploaded_by != current_user.id and template.visibility != "public":
        raise HTTPException(status_code=403, detail="You do not have access to this template")
    return template


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
        raise HTTPException(status_code=400, detail="Template name must be 100 characters or fewer")

    # 5. Validate category
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400, 
            detail="Invalid category. Allowed: notice, mom, report, application, letter, certificate, proposal, invoice, custom"
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
        logger.error(f"DB error while creating template record: {e}. Rolling back file.")
        await asyncio.to_thread(storage_service.delete_file, stored.path)
        raise HTTPException(status_code=500, detail="Could not save template record") from None

    return template
