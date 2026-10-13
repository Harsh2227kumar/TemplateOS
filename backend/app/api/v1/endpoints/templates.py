"""
Template core routes: list / library / access-options / get / access /
delete / field list / upload.

Router modules under the /templates prefix (included in this order by
app/api/v1/api.py, which preserves the original route order):
  templates             -> this module (static /library and /access-options
                           are declared BEFORE /{template_id})
  template_placeholders -> detect-placeholders, fix-placeholders
  template_cleaning     -> content, clean-suggestions, clean-preview, clean
  template_ai           -> suggest-fields
  template_fields       -> field editor (create / reorder / update / delete / sync)
Shared helpers live in _template_common.
"""

import logging
import zipfile
from io import BytesIO

from fastapi import APIRouter, Form, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._template_common import require_manage
from app.services.storage_service import StorageError, storage_service
from app.services.template_access import (
    ASSIGNABLE_ROLES,
    DEPARTMENT_PUBLISHERS,
    ORG_PUBLISHERS,
    ROLE_LABELS,
    PublishRuleError,
    can_manage,
    clean_scope,
    normalize_scope,
    parse_roles_csv,
    resolve_publish_access,
    user_can_view_template,
)
from app.crud.template_crud import (
    create_template,
    get_templates_by_user,
    get_template_by_id,
    get_library_templates,
)
from app.crud.template_field_crud import get_fields_by_template
from app.schemas.template import (
    TemplateAccessOptions,
    TemplateAccessUpdate,
    TemplateCreate,
    TemplateResponse,
    TemplateListItem,
    TemplateLibraryResponse,
)
from app.schemas.template_field import TemplateFieldRead
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


def _template_response(template: Template, user: User) -> TemplateResponse:
    """TemplateResponse with `can_manage` computed for the requesting user."""
    response = TemplateResponse.model_validate(template)
    response.can_manage = can_manage(user, template)
    return response


def _list_item(template: Template, user: User) -> TemplateListItem:
    item = TemplateListItem.model_validate(template)
    item.can_manage = can_manage(user, template)
    return item

def _publish_error(exc: PublishRuleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


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
        "templates": [_list_item(template, current_user) for template in templates],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/", response_model=list[TemplateListItem])
def list_my_templates(
    current_user: CurrentUser,
    db: DbSession,
) -> list[TemplateListItem]:
    """Return all templates uploaded by the current user, newest first."""
    return [
        _list_item(template, current_user)
        for template in get_templates_by_user(db, current_user.id)
    ]


# Declared BEFORE /{template_id} so "access-options" is not parsed as an id.
@router.get("/access-options", response_model=TemplateAccessOptions)
def get_access_options(
    current_user: CurrentUser,
    db: DbSession,
) -> TemplateAccessOptions:
    """
    Choices for the upload / manage-access audience pickers.

    - roles: every role a template can be restricted to (no super_admin).
    - organizations / departments: distinct non-empty values from user
      profiles. super_admin gets all of them; everyone else only sees their
      own organization (they can never publish anywhere else).
    - can_publish: which scoped visibilities the current user may use.
    - defaults: the current user's own organization / department.
    """
    rows = db.execute(select(User.organization, User.department).distinct()).all()
    own_org = normalize_scope(current_user.organization)
    see_all = current_user.role == "super_admin"

    organizations: dict[str, str] = {}
    departments: dict[tuple[str, str], dict] = {}
    for organization, department in rows:
        org = clean_scope(organization)
        dept = clean_scope(department)
        if not see_all and normalize_scope(org) != own_org:
            continue
        if org is not None:
            organizations.setdefault(normalize_scope(org), org)
        if dept is not None:
            departments.setdefault(
                (normalize_scope(org), normalize_scope(dept)),
                {"organization": org, "department": dept},
            )

    return TemplateAccessOptions(
        roles=[
            {"value": role, "label": ROLE_LABELS.get(role, role)}
            for role in ASSIGNABLE_ROLES
        ],
        organizations=sorted(organizations.values(), key=str.lower),
        departments=sorted(
            departments.values(),
            key=lambda d: ((d["organization"] or "").lower(), d["department"].lower()),
        ),
        can_publish={
            "organization": current_user.role in ORG_PUBLISHERS,
            "department": current_user.role in DEPARTMENT_PUBLISHERS,
        },
        defaults={
            "organization": clean_scope(current_user.organization),
            "department": clean_scope(current_user.department),
        },
    )


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> TemplateResponse:
    """Return a single template by ID if the user may view it (template_access)."""
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not user_can_view_template(current_user, template):
        raise HTTPException(
            status_code=403, detail="You do not have access to this template"
        )
    return _template_response(template, current_user)


@router.patch("/{template_id}/access", response_model=TemplateResponse)
def update_template_access(
    template_id: int,
    request: TemplateAccessUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TemplateResponse:
    """
    Change who can see / use a template: visibility, scope and role
    restriction. Requires can_manage; the publish rules are applied for the
    ACTING user (e.g. an org_admin can only scope to their own organization).
    """
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    require_manage(template, current_user, "change access to")

    try:
        resolved = resolve_publish_access(
            current_user,
            request.visibility,
            request.scope_organization,
            request.scope_department,
            request.allowed_roles,
        )
    except PublishRuleError as exc:
        raise _publish_error(exc) from None

    template.visibility = resolved.visibility
    template.scope_organization = resolved.scope_organization
    template.scope_department = resolved.scope_department
    template.allowed_roles = resolved.allowed_roles
    db.commit()
    db.refresh(template)
    logger.info(
        f"Access for template {template_id} set to {resolved.visibility} "
        f"(org={resolved.scope_organization!r}, dept={resolved.scope_department!r}, "
        f"roles={resolved.allowed_roles}) by user {current_user.id}"
    )
    return _template_response(template, current_user)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Permanently delete a template: the DB record (fields cascade) and every
    stored file (original + processed). Super-admin only — a destructive,
    irreversible action that also removes every user's documents, so it is
    deliberately NOT part of can_manage: owners and org/department admins
    cannot delete (they can make a template private instead).
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
            storage_service.delete_file(relative_path)
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
def upload_template(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    name: str = Form(default=""),
    description: str | None = Form(default=None),
    category: str = Form(...),
    visibility: str = Form(...),
    scope_organization: str | None = Form(default=None),
    scope_department: str | None = Form(default=None),
    allowed_roles: str | None = Form(
        default=None, description="Comma-separated roles; empty = everyone in scope"
    ),
) -> TemplateResponse:
    # Audited V1.2 Phase 2 — all validation, storage, and DB logic verified
    # 1. Validate file type
    filename = file.filename or "template.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX files are accepted")

    # 2. Read (bounded: never load more than the limit + 1 byte) + empty check
    content = file.file.read(MAX_FILE_SIZE_BYTES + 1)
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

    # 6b. Audience / publish rules (checked before anything is written to disk)
    try:
        access = resolve_publish_access(
            current_user,
            visibility,
            scope_organization,
            scope_department,
            parse_roles_csv(allowed_roles),
        )
    except PublishRuleError as exc:
        raise _publish_error(exc) from None

    # 7. Save file via storage_service (in thread pool)
    try:
        logger.info(f"Saving template {filename} for user {current_user.id}")
        stored = storage_service.save_bytes("templates_original", filename, content)
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
        scope_organization=access.scope_organization,
        scope_department=access.scope_department,
        allowed_roles=access.allowed_roles,
    )

    try:
        template = create_template(db, template_data)
        logger.info(f"Created template record {template.id} for user {current_user.id}")
    except Exception as e:
        logger.error(
            f"DB error while creating template record: {e}. Rolling back file."
        )
        storage_service.delete_file(stored.path)
        raise HTTPException(
            status_code=500, detail="Could not save template record"
        ) from None

    return _template_response(template, current_user)
