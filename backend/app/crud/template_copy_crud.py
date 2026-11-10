"""
Personal template copies (V1.7 Phase 2.1 - "Customize for me").

A user who may view a template (e.g. faculty using the admin's MoM) gets
their own private copy to change: new stored copies of the original and
fill-ready files, the same fields, `parent_template_id` pointing at the
original and a first revision with source "customize". The original
template, its fields, files and drafts are never touched.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crud.template_field_crud import get_fields_by_template
from app.crud.template_revision_crud import add_revision
from app.models.template import Template
from app.models.template_field import TemplateField
from app.models.user import User
from app.services.docx_cleaner import get_renderable_path
from app.services.storage_service import storage_service

COPY_SUFFIX = "(my copy)"
NAME_MAX_LENGTH = 100
# Copies of archived / locked templates start as a normal usable template.
_RESET_STATUSES = {"archived": "active", "locked": "active"}
_FIELD_COLUMNS_SKIPPED = {"id", "template_id", "created_at", "updated_at"}


def copy_name(db: Session, template: Template, user: User) -> str:
    """'<name> (my copy)', numbered '(my copy 2)' ... when the user has more copies."""
    existing = db.execute(
        select(func.count())
        .select_from(Template)
        .where(Template.parent_template_id == template.id, Template.uploaded_by == user.id)
    ).scalar_one()
    suffix = COPY_SUFFIX if existing == 0 else f"(my copy {existing + 1})"
    base = template.name[: NAME_MAX_LENGTH - len(suffix) - 1].rstrip()
    return f"{base} {suffix}"


def _copy_file(path: str | None, category: str, filename: str) -> str | None:
    if not path:
        return None
    stored = storage_service.save_bytes(category, filename, storage_service.read_bytes(path))
    return stored.path


def copy_template_for_user(db: Session, template: Template, user: User) -> Template:
    """
    Create the user's private copy of `template` (flushed, not committed).
    Stored files are copied first; the caller deletes them on rollback via
    the returned template's paths (see stored_paths()).
    """
    filename = template.original_filename or "template.docx"
    original_path = _copy_file(template.original_file_path, "templates_original", filename)
    processed_path = None
    if template.processed_file_path:
        processed_path = _copy_file(template.processed_file_path, "templates_processed", filename)

    copy = Template(
        name=copy_name(db, template, user),
        description=template.description,
        category=template.category,
        visibility="private",
        status=_RESET_STATUSES.get(template.status, template.status),
        original_file_path=original_path,
        processed_file_path=processed_path,
        original_filename=template.original_filename,
        file_size_bytes=template.file_size_bytes,
        file_extension=template.file_extension,
        uploaded_by=user.id,
        organization_id=user.organization_id,
        department_id=user.department_id,
        version=1,
        is_locked=False,
        requires_approval=template.requires_approval,
        parent_template_id=template.id,
    )
    db.add(copy)
    db.flush()

    columns = [c.key for c in TemplateField.__table__.columns if c.key not in _FIELD_COLUMNS_SKIPPED]
    for source_field in get_fields_by_template(db, template.id):
        db.add(
            TemplateField(
                template_id=copy.id,
                **{column: getattr(source_field, column) for column in columns},
            )
        )
    db.flush()

    renderable = get_renderable_path(copy)
    if renderable:
        add_revision(
            db,
            copy,
            source="customize",
            file_path=renderable,
            created_by=user.id,
            note=f"Copy of template #{template.id}",
        )
    return copy


def stored_paths(template: Template) -> list[str]:
    """The stored files a copy created (for cleanup when its transaction fails)."""
    return [p for p in (template.original_file_path, template.processed_file_path) if p]
