"""
Length budgets for template fields (V1.7 Phase 2.2 - Member 3).

Where a placeholder sits in the Word file decides how much text fits there:
inside a sentence, on its own line, in a table cell, in a header / footer or
in a text box. The AI fill assistant is told the budget and the fit check
reports values that exceed it. Budgets are HINTS: nothing is ever cut.

- field_budgets(docx_bytes, fields)       pure: placement + budget per field
- cached_field_budgets(template, fields)  reads the template's fill-ready file
                                          once per template version

A field's validation_rule "max:N" overrides the default (hard=True); for list
fields N is the item count. date / number / signature fields have no budget.
"""

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Iterable

from app.services.docx_parser import (
    PLACEHOLDER_PATTERN,
    STATEMENT_PATTERN,
    VALID_KEY_PATTERN,
    _FOR,
    _load,
    normalize_token,
)
from app.services.docx_walker import walk_document

if TYPE_CHECKING:
    from app.models.template import Template
    from app.models.template_field import TemplateField

logger = logging.getLogger(__name__)

PLACEMENTS: tuple[str, ...] = ("inline", "line", "table_cell", "header_footer", "textbox")
BUDGET_FIELD_TYPES: tuple[str, ...] = ("text", "textarea", "list")

# Default character budgets per placement: (text, textarea).
CHAR_BUDGETS: dict[str, tuple[int, int]] = {
    "inline": (80, 80),
    "line": (200, 1200),
    "table_cell": (120, 400),
    "header_footer": (60, 60),
    "textbox": (150, 150),
}
# List fields: (items, characters per item).
LIST_BUDGET = (10, 200)
LIST_BUDGET_TABLE = (8, 120)

# More than this many other characters next to the tag: the placeholder is
# part of a sentence ("Name: {{ student_name }}"), not a line of its own.
INLINE_MIN_OTHER_CHARS = 3
_TAGS = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_FILLER = re.compile(r"[\s:;,.\-_–—()\[\]|/]+")
_MAX_RULE = re.compile(r"(?:^|\|)\s*max:(\d+)\s*(?:\||$)")

_CACHE_SIZE = 64
_cache: "OrderedDict[tuple, dict[str, FieldBudget]]" = OrderedDict()
_cache_lock = Lock()


@dataclass(frozen=True)
class FieldBudget:
    field_name: str
    placement: str
    budget: int
    unit: str  # "chars" | "items"
    item_budget: int | None = None  # list fields: characters per item
    hard: bool = False  # True when the budget comes from validation_rule max:N


def _placement(slot) -> str:
    if slot.location == "table":
        return "table_cell"
    if slot.location in ("header", "footer"):
        return "header_footer"
    if slot.location == "textbox":
        return "textbox"
    other = _FILLER.sub("", _TAGS.sub("", slot.text))
    return "inline" if len(other) > INLINE_MIN_OTHER_CHARS else "line"


def placements(docx_bytes: bytes) -> dict[str, str]:
    """{field key: placement} of each key's FIRST occurrence in the DOCX."""
    found: dict[str, str] = {}
    dmap = walk_document(_load(docx_bytes))
    for slot in dmap.slots:
        tokens: list[tuple[int, str]] = []
        for match in PLACEHOLDER_PATTERN.finditer(slot.text):
            key = normalize_token(match.group(1))
            if key:
                tokens.append((match.start(), key))
        for match in STATEMENT_PATTERN.finditer(slot.text):
            loop = _FOR.match(match.group(1) or match.group(2) or "")
            if loop and VALID_KEY_PATTERN.match(loop.group(3)):
                tokens.append((match.start(), loop.group(3)))
        if not tokens:
            continue
        placement = _placement(slot)
        for _, key in sorted(tokens):
            found.setdefault(key, placement)
    return found


def _max_rule(rule: str | None) -> int | None:
    match = _MAX_RULE.search(rule or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def _budget_for(field: "TemplateField", placement: str) -> FieldBudget | None:
    if field.field_type not in BUDGET_FIELD_TYPES:
        return None
    hard_max = _max_rule(field.validation_rule)
    if field.field_type == "list":
        items, per_item = LIST_BUDGET_TABLE if placement == "table_cell" else LIST_BUDGET
        return FieldBudget(
            field_name=field.field_name,
            placement=placement,
            budget=hard_max or items,
            unit="items",
            item_budget=per_item,
            hard=hard_max is not None,
        )
    text_budget, textarea_budget = CHAR_BUDGETS[placement]
    default = textarea_budget if field.field_type == "textarea" else text_budget
    return FieldBudget(
        field_name=field.field_name,
        placement=placement,
        budget=hard_max or default,
        unit="chars",
        hard=hard_max is not None,
    )


def field_budgets(
    docx_bytes: bytes | None, fields: Iterable["TemplateField"]
) -> dict[str, FieldBudget]:
    """
    Budget per field (text / textarea / list only). A missing or unreadable
    file, and fields not found in the file, use the "line" placement. Never
    raises.
    """
    found: dict[str, str] = {}
    if docx_bytes:
        try:
            found = placements(docx_bytes)
        except Exception as exc:  # broken DOCX: defaults are still useful
            logger.warning("Field placement could not read the template file: %s", exc)
    budgets: dict[str, FieldBudget] = {}
    for field in fields:
        budget = _budget_for(field, found.get(field.field_name, "line"))
        if budget is not None:
            budgets[field.field_name] = budget
    return budgets


def cached_field_budgets(
    template: "Template", fields: Iterable["TemplateField"]
) -> dict[str, FieldBudget]:
    """
    field_budgets for the template's fill-ready file, cached per template
    version and field configuration (LRU, in memory).
    """
    # Imported here: docx_cleaner / storage are heavier than this module needs
    # for its pure part (and tests of field_budgets do not touch storage).
    from app.services.docx_cleaner import get_renderable_path
    from app.services.storage_service import storage_service

    fields = list(fields)
    path = get_renderable_path(template)
    key = (
        template.id,
        template.version,
        path,
        tuple((f.field_name, f.field_type, f.validation_rule) for f in fields),
    )
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached

    docx_bytes: bytes | None = None
    if path:
        try:
            docx_bytes = storage_service.read_bytes(path)
        except Exception as exc:  # missing file: defaults
            logger.warning("Template file for budgets is not readable: %s", exc)
    budgets = field_budgets(docx_bytes, fields)
    with _cache_lock:
        _cache[key] = budgets
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return budgets


def clear_budget_cache() -> None:
    with _cache_lock:
        _cache.clear()


def value_length(budget: FieldBudget, value: str | None, items: list[str] | None = None) -> int:
    """What is compared with budget.budget: characters, or the item count."""
    if budget.unit == "items":
        return len(items or [])
    return len(value or "")


def is_over_budget(budget: FieldBudget, value: str | None, items: list[str] | None = None) -> bool:
    if budget.unit == "items":
        items = items or []
        if len(items) > budget.budget:
            return True
        return budget.item_budget is not None and any(len(i) > budget.item_budget for i in items)
    return len(value or "") > budget.budget
