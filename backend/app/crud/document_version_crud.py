"""
CRUD helpers for document_versions (V1.7 Phase 2 - Member 3).

Member 2's endpoints and the generation flow call these:
- snapshot_values           -> the values a new version is rendered from
- create_version            -> POST /documents/{id}/generate (version N+1)
- list_versions / get_version -> GET /documents/{id}/versions[/{n}]
- parse_snapshot / diff_snapshots -> changed_fields between versions
- restore_values            -> POST /documents/{id}/versions/{n}/restore
- prune_old_version_files   -> retention after a generate

None of them commit: the caller commits once with its other changes, then
deletes the returned storage paths (after commit, never inside the
transaction; see app.services.generated_file_cleanup).
"""

import json
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utc_now_naive
from app.crud.document_value_crud import apply_value
from app.models.document import Document
from app.models.document_value import DocumentValue
from app.models.document_version import DocumentVersion
from app.models.generated_file import GeneratedFile
from app.services.rich_text import parse_stored

SNAPSHOT_KEYS = ("field_name", "value", "value_format", "rich_content", "ai_modified", "ai_action")


def snapshot_values(document: Document) -> list[dict]:
    """
    The document's saved values as a self-contained snapshot, sorted by
    field_name: [{field_name, value, value_format, rich_content (dict |
    None), ai_modified, ai_action}].
    """
    items = []
    for row in document.values:
        rich = row.value_format == "rich"
        items.append(
            {
                "field_name": row.field_name,
                "value": row.value,
                "value_format": row.value_format or "plain",
                "rich_content": parse_stored(row.rich_content) if rich else None,
                "ai_modified": bool(row.ai_modified),
                "ai_action": row.ai_action if row.ai_modified else None,
            }
        )
    return sorted(items, key=lambda item: item["field_name"])


def dump_snapshot(snapshot: list[dict]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))


def parse_snapshot(version_or_text: DocumentVersion | str | None) -> list[dict]:
    """A stored snapshot as a list of complete items (missing keys defaulted)."""
    text = (
        version_or_text.values_snapshot
        if isinstance(version_or_text, DocumentVersion)
        else version_or_text
    )
    if not text:
        return []
    try:
        raw = json.loads(text)
    except ValueError:
        return []
    items = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("field_name"), str):
            continue
        value_format = item.get("value_format") if item.get("value_format") in ("plain", "rich") else "plain"
        rich_content = item.get("rich_content")
        if isinstance(rich_content, str):
            rich_content = parse_stored(rich_content)
        ai_modified = bool(item.get("ai_modified"))
        items.append(
            {
                "field_name": item["field_name"],
                "value": item.get("value") if isinstance(item.get("value"), str) else "",
                "value_format": value_format,
                "rich_content": rich_content if value_format == "rich" and isinstance(rich_content, dict) else None,
                "ai_modified": ai_modified,
                "ai_action": item.get("ai_action") if ai_modified else None,
            }
        )
    return sorted(items, key=lambda entry: entry["field_name"])


def _next_version_number(db: Session, document_id: int) -> int:
    current = db.execute(
        select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == document_id)
    ).scalar_one()
    return (current or 0) + 1


def create_version(
    db: Session,
    document: Document,
    created_by: int | None,
    template_version: int | None,
    note: str | None = None,
    snapshot: list[dict] | None = None,
    created_at: datetime | None = None,
) -> DocumentVersion:
    """
    Add version max(version)+1 with a snapshot of the document's values
    (flushed, not committed).

    A concurrent generate may take the same number: on IntegrityError the
    session is rolled back and the next number is tried once more. Call it
    before making other changes in the session, because that rollback
    discards them; pass `snapshot` taken before the call to keep it stable.
    """
    document_id = document.id
    snapshot_text = dump_snapshot(snapshot if snapshot is not None else snapshot_values(document))
    for attempt in range(2):
        version = DocumentVersion(
            document_id=document_id,
            version=_next_version_number(db, document_id),
            created_by=created_by,
            created_at=created_at or utc_now_naive(),
            template_version=template_version,
            values_snapshot=snapshot_text,
            note=note,
        )
        db.add(version)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
            continue
        return version
    raise AssertionError("unreachable")  # pragma: no cover


def list_versions(db: Session, document_id: int) -> list[DocumentVersion]:
    """All versions of a document, newest first, with files and creator loaded."""
    return list(
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
            .options(
                selectinload(DocumentVersion.generated_file),
                selectinload(DocumentVersion.creator),
            )
        )
        .scalars()
        .all()
    )


def get_version(db: Session, document_id: int, version: int) -> DocumentVersion | None:
    return db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.version == version)
        .options(
            selectinload(DocumentVersion.generated_file),
            selectinload(DocumentVersion.creator),
        )
    ).scalar_one_or_none()


def latest_version_number(db: Session, document_id: int) -> int | None:
    """The highest version number, None before the first generate."""
    return db.execute(
        select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == document_id)
    ).scalar_one()


def count_versions(db: Session, document_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == document_id)
    ).scalar_one()


def diff_snapshots(prev: list[dict] | None, curr: list[dict]) -> list[str]:
    """
    field_names whose value, format or rich content differ between two
    snapshots (added or removed fields count as changed), sorted. The first
    version (prev None) has no changed fields.
    """
    if prev is None:
        return []
    before = {item["field_name"]: item for item in prev}
    after = {item["field_name"]: item for item in curr}
    changed = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old is None or new is None:
            changed.append(name)
        elif any(old.get(key) != new.get(key) for key in ("value", "value_format", "rich_content")):
            changed.append(name)
    return changed


def changed_fields_by_version(versions: list[DocumentVersion]) -> dict[int, list[str]]:
    """{version number: changed field_names vs the previous version} for a full list."""
    ordered = sorted(versions, key=lambda v: v.version)
    result: dict[int, list[str]] = {}
    previous: list[dict] | None = None
    for version in ordered:
        snapshot = parse_snapshot(version)
        result[version.version] = diff_snapshots(previous, snapshot)
        previous = snapshot
    return result


def restore_values(db: Session, document: Document, version: DocumentVersion) -> list[DocumentValue]:
    """
    Make the document's saved values equal to the version's snapshot (not
    committed): upsert every snapshot item, delete values of fields absent
    from the snapshot, bump document.updated_at. AI flags are restored as
    they were saved (ai_modified_at = now for AI values).
    """
    now = utc_now_naive()
    snapshot = parse_snapshot(version)
    names = {item["field_name"] for item in snapshot}
    rows = {
        row.field_name: row
        for row in db.execute(
            select(DocumentValue).where(DocumentValue.document_id == document.id)
        ).scalars()
    }
    result = []
    for item in snapshot:
        row = rows.get(item["field_name"])
        if row is None:
            row = DocumentValue(document_id=document.id, field_name=item["field_name"])
            db.add(row)
        else:
            row.ai_modified = False  # restored flags get a fresh timestamp
        apply_value(row, item, now)
        row.updated_at = now
        result.append(row)
    absent = [name for name in rows if name not in names]
    if absent:
        db.execute(
            delete(DocumentValue).where(
                DocumentValue.document_id == document.id,
                DocumentValue.field_name.in_(absent),
            )
        )
    document.updated_at = now
    db.flush()
    db.expire(document, ["values"])
    return result


def prune_old_version_files(db: Session, document_id: int, keep: int) -> list[str]:
    """
    Retention: mark the generated files of every version older than the
    newest `keep` as pruned (files_pruned_at = now; not committed) and
    return their DOCX/PDF storage paths for deletion after commit. Rows,
    snapshots and the recorded paths are kept; already pruned versions are
    skipped.
    """
    keep = max(1, keep)
    rows = db.execute(
        select(GeneratedFile)
        .join(DocumentVersion, DocumentVersion.id == GeneratedFile.version_id)
        .where(GeneratedFile.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
    ).scalars().all()
    now = utc_now_naive()
    paths: list[str] = []
    for row in rows[keep:]:
        if row.files_pruned_at is not None:
            continue
        row.files_pruned_at = now
        paths.extend(path for path in (row.docx_path, row.pdf_path) if path)
    db.flush()
    return paths
