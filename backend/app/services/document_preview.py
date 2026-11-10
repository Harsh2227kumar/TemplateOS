"""
V1.7 Phase 1 - Preview helpers (pure: no DB session, no FastAPI).

GET /documents/{id}/preview shows every field exactly as the generated
document will show it. These helpers turn a template's fields and a
document's saved values into the preview's sections and completeness, using
the SAME rules as the rest of the app:

- Sections (edit form, edit-document-page.tsx): fields ordered by
  (display_order, id); a null / blank section is "General"; sections appear
  in the order of their first field.
- Labels (edit form): field_label when set, else the raw field_name.
- Emptiness (save validator, document_validator.py): text is empty when
  blank after strip(); a list is empty when it has no non-blank item.
- Values (generation, document_generation.py): only SAVED values count. A
  never-saved field renders blank and fails the required check, even when
  the template field has a default_value (the form pre-fills defaults, but
  they only reach the document once saved).
- Formatting: injected as `format_value(field, raw) -> str` so the rule
  stays in app.services.generation_service (dates DD-MM-YYYY, lists one
  item per line). It is only called for non-empty values.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING

from app.schemas.document_preview import (
    PreviewCompleteness,
    PreviewField,
    PreviewSection,
)
from app.services.document_validator import _parse_list_value
from app.services.generation_service import parse_list_value

if TYPE_CHECKING:
    from app.models.document_value import DocumentValue
    from app.models.template_field import TemplateField

GENERAL_SECTION = "General"

# format_value(field, raw) -> display string, e.g. a thin wrapper around
# generation_service.build_context([field], {field.field_name: raw}).
FormatValue = Callable[["TemplateField", str], str]


def saved_values(values: Iterable["DocumentValue"]) -> dict[str, str]:
    """document.values -> {field_name: raw value} (the values_by_name argument)."""
    return {value.field_name: value.value for value in values}


def field_label(field: "TemplateField") -> str:
    """The form's label: field_label (trimmed) when set, else field_name."""
    return (field.field_label or "").strip() or field.field_name


def section_name(field: "TemplateField") -> str:
    return (field.section or "").strip() or GENERAL_SECTION


def ordered_fields(fields: Iterable["TemplateField"]) -> list["TemplateField"]:
    """Fields in form order: (display_order, id)."""
    return sorted(fields, key=lambda f: (f.display_order or 0, f.id or 0))


def list_items(raw: str | None) -> list[str]:
    """
    A stored list value as its non-blank items, exactly as generation renders
    them (generation_service.parse_list_value): JSON array -> items; invalid
    JSON -> [raw] when not blank; None / blank -> [].
    """
    if raw is None:
        return []
    return parse_list_value(raw)


def field_is_empty(field_type: str, raw: str | None) -> bool:
    """
    The save validator's emptiness rule (document_validator.py).

    None / blank -> empty. list: a JSON array of strings is empty when no
    item is non-blank (["", " "] is empty). A list value the validator would
    reject (not a JSON array of strings) counts as one item, the raw text,
    so it is empty only when blank; that matches what generation prints.
    """
    if raw is None or not raw.strip():
        return True
    if field_type != "list":
        return False
    items = _parse_list_value(raw)
    if items is None:
        return False  # raw is non-blank: treated as a single item
    return not any(item.strip() for item in items)


def build_field(
    field: "TemplateField",
    raw: str | None,
    format_value: FormatValue,
) -> PreviewField:
    is_list = field.field_type == "list"
    is_empty = field_is_empty(field.field_type, raw)
    return PreviewField(
        field_name=field.field_name,
        label=field_label(field),
        field_type=field.field_type,
        is_required=bool(field.is_required),
        ai_enabled=bool(field.ai_enabled),
        display_order=field.display_order or 0,
        value=raw,
        display_value="" if is_empty else format_value(field, raw),
        items=list_items(raw) if is_list else None,
        is_empty=is_empty,
        missing_required=bool(field.is_required) and is_empty,
    )


def build_sections(
    fields: Iterable["TemplateField"],
    values_by_name: Mapping[str, str],
    format_value: FormatValue,
) -> list[PreviewSection]:
    """
    Group the template's fields into the form's sections.

    values_by_name: {field_name: saved raw value}; a missing key means the
    field was never saved (value=None, empty). format_value(field, raw) is
    generation's formatter, called only for non-empty values.
    """
    sections: dict[str, list[PreviewField]] = {}
    for field in ordered_fields(fields):
        raw = values_by_name.get(field.field_name)
        sections.setdefault(section_name(field), []).append(
            build_field(field, raw, format_value)
        )
    return [PreviewSection(name=name, fields=items) for name, items in sections.items()]


def compute_completeness(
    fields: Iterable["TemplateField"],
    values_by_name: Mapping[str, str],
) -> PreviewCompleteness:
    """Required fields filled vs total; missing_required in display order."""
    required = [field for field in ordered_fields(fields) if field.is_required]
    missing = [
        field.field_name
        for field in required
        if field_is_empty(field.field_type, values_by_name.get(field.field_name))
    ]
    return PreviewCompleteness(
        required_total=len(required),
        required_filled=len(required) - len(missing),
        missing_required=missing,
    )
