"""
CRUD helpers for template_revisions (V1.7 Phase 2.1 - Member 3).

- add_revision        -> record a change of a template's fill-ready file
                         (clean, fix placeholders, personal copy, manual edit
                         in ONLYOFFICE, restore); not committed
- list_revisions / get_revision -> history and restore
- field_changes       -> what the current file means for the form: new
                         placeholders, fields whose placeholder is gone,
                         blanks the clean step could turn into fields, and
                         whether docxtpl can render the file at all

Revisions reference stored files; a stored template file is never
overwritten or deleted while its template exists (see
generated_file_cleanup for deletion with the template).
"""

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.crud.template_field_crud import get_fields_by_template
from app.models.template import Template
from app.models.template_revision import TemplateRevision
from app.services.docx_cleaner import get_renderable_path
from app.services.docx_parser import get_template_variables
from app.services.field_inference import infer_field_meta
from app.services.storage_service import StorageError, storage_service

logger = logging.getLogger(__name__)

# Clean-suggestion groups that mark a spot to fill in (a new field).
FILLABLE_GROUPS = frozenset({"blanks", "empty_values", "brackets"})


@dataclass
class AddedPlaceholder:
    key: str
    suggested_label: str
    suggested_type: str


@dataclass
class FieldChanges:
    revision: int
    added: list[AddedPlaceholder] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    blank_suggestions: int = 0
    renderable: bool = True
    render_error: str | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.blank_suggestions)


def count_blank_suggestions(docx_bytes: bytes) -> int:
    """Spots the clean step would offer to turn into fields (0 when analysis fails)."""
    from app.services.clean_suggester import suggest_cleaning

    try:
        report = suggest_cleaning(docx_bytes)
    except Exception:  # analysis is advisory; never block saving a revision
        logger.warning("Clean suggestions failed while recording a template revision", exc_info=True)
        return 0
    return sum(1 for suggestion in report.suggestions if suggestion.group in FILLABLE_GROUPS)


def _placeholder_names(docx_bytes: bytes) -> tuple[set[str], str | None]:
    names, error = get_template_variables(docx_bytes)
    return (names or set()), error


def add_revision(
    db: Session,
    template: Template,
    *,
    source: str,
    file_path: str,
    created_by: int | None,
    note: str | None = None,
    docx_bytes: bytes | None = None,
) -> TemplateRevision:
    """
    Record revision `template.version` (the caller increments the version
    first when the file changed) for the stored file `file_path`.
    placeholders_added / removed compare the file's placeholders with the
    template's current fields. Flushed, not committed.
    """
    if docx_bytes is None:
        docx_bytes = storage_service.read_bytes(file_path)
    names, _error = _placeholder_names(docx_bytes)
    field_names = {f.field_name for f in get_fields_by_template(db, template.id)}
    revision = TemplateRevision(
        template_id=template.id,
        revision=template.version or 1,
        source=source,
        file_path=file_path,
        created_by=created_by,
        placeholders_added=json.dumps(sorted(names - field_names)),
        placeholders_removed=json.dumps(sorted(field_names - names)),
        blank_suggestions=count_blank_suggestions(docx_bytes),
        note=(note or None) and note[:255],
    )
    db.add(revision)
    db.flush()
    return revision


def list_revisions(db: Session, template_id: int) -> list[TemplateRevision]:
    """All revisions of a template, newest first, with their creator."""
    return list(
        db.execute(
            select(TemplateRevision)
            .where(TemplateRevision.template_id == template_id)
            .order_by(TemplateRevision.revision.desc())
            .options(selectinload(TemplateRevision.creator))
        )
        .scalars()
        .all()
    )


def get_revision(db: Session, template_id: int, revision: int) -> TemplateRevision | None:
    return db.execute(
        select(TemplateRevision)
        .where(TemplateRevision.template_id == template_id, TemplateRevision.revision == revision)
        .options(selectinload(TemplateRevision.creator))
    ).scalar_one_or_none()


def field_changes(db: Session, template: Template) -> FieldChanges:
    """
    Compare the template's current fill-ready file with its fields (read only).
    A file docxtpl cannot parse reports renderable=False with the error.
    """
    changes = FieldChanges(revision=template.version or 1)
    path = get_renderable_path(template)
    if not path:
        changes.renderable = False
        changes.render_error = "The template has no file"
        return changes
    try:
        docx_bytes = storage_service.read_bytes(path)
    except StorageError:
        changes.renderable = False
        changes.render_error = "The template file is missing on the server"
        return changes
    names, error = _placeholder_names(docx_bytes)
    if error:
        changes.renderable = False
        changes.render_error = error
    field_names = {f.field_name for f in get_fields_by_template(db, template.id)}
    for key in sorted(names - field_names):
        meta = infer_field_meta(key)
        changes.added.append(
            AddedPlaceholder(key=key, suggested_label=meta.field_label, suggested_type=meta.field_type)
        )
    if not error:
        changes.removed = sorted(field_names - names)
    changes.blank_suggestions = count_blank_suggestions(docx_bytes)
    return changes
