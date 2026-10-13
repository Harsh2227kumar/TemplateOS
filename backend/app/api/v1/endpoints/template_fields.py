"""
Field editor routes (owner-only writes): create, reorder, update, delete
and bulk-sync a template's fields. The read-only field list
(GET /{template_id}/fields) is declared in templates.py to keep the
original route order.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._template_common import require_manage
from app.crud.template_crud import advance_status, get_template_by_id
from app.crud.template_field_crud import (
    create_field,
    delete_field,
    field_exists,
    get_field_by_id,
    get_fields_by_template,
    move_field_to,
    reorder_fields,
    sync_fields,
    update_field,
)
from app.models.template import Template
from app.models.template_field import TemplateField
from app.models.user import User
from app.schemas.template_field import (
    FieldReorderRequest,
    FieldSyncRequest,
    TemplateFieldCreate,
    TemplateFieldRead,
    TemplateFieldUpdate,
    VALIDATION_RULE_HELP,
    check_validation_rule,
)
from app.services import docx_parser
from app.services.field_inference import infer_field_meta

router = APIRouter()
logger = logging.getLogger(__name__)


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
    require_manage(template, current_user, "edit fields of")
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
