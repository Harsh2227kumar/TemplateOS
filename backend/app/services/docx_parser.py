"""
DOCX placeholder detection service (V1.3 Phase 1 — template pipeline).

Pure parsing — NO database access. The detection endpoint
(app/api/v1/endpoints/templates.py) persists through template_field_crud
using this module's DetectionResult.

Design (detect/generate parity):
- docxtpl (the SAME Jinja2 engine that renders documents) provides the
  AUTHORITATIVE placeholder set via get_undeclared_template_variables().
- A permissive scan over every paragraph (body, tables incl. merged/nested
  cells, text boxes, headers/footers — see docx_walker) provides ordering,
  duplicate counts, the nearest heading per key, and malformed-token
  warnings ({{Bad Name}}) that Jinja cannot parse.

Token tolerance: {{key}}, {{  key  }}, {{ key|default('') }}, {{ obj.attr }},
{{r key }} (docxtpl rich text) all resolve to the key before the filter /
attribute. {% for x in items %} / {% if flag %} register `items` / `flag`
(in document order) and loop variables are never reported as fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import TypedDict

from docxtpl import DocxTemplate

from app.services.docx_walker import walk_document
from app.services.field_inference import (
    key_to_label,
    suggest_key as _suggest_key,
)

# Permissive on purpose: must ALSO catch invalid names like "{{Meeting Title}}"
# so the UI can warn (docxtpl/Jinja2 reject those outright).
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
STATEMENT_PATTERN = re.compile(r"\{%-?\s*(?:p|tr|tc|r)?\s+(.+?)\s*-?%\}|\{%-?\s*(.+?)\s*-?%\}")

# A valid placeholder key: lowercase snake_case, starts with a letter.
VALID_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_INVALID_NAME_REASON = (
    "Placeholder names must be lowercase snake_case "
    "(letters, digits, underscores) and start with a letter"
)
_FOR = re.compile(r"^for\s+([A-Za-z_]\w*)(?:\s*,\s*([A-Za-z_]\w*))?\s+in\s+([A-Za-z_][\w]*)")
_IF = re.compile(r"^(?:if|elif)\s+(?:not\s+)?([A-Za-z_]\w*)")
_JINJA_NAMES = {"loop", "true", "false", "none", "range", "caller", "super"}


class TextSegment(TypedDict):
    index: int
    location: str  # "body" | "table" | "header" | "footer" | "textbox"
    text: str


@dataclass(frozen=True)
class DetectedField:
    """A valid placeholder key, in first-seen document order."""

    key: str
    display_order: int
    section: str | None = None
    location: str | None = None
    type_hint: str | None = None  # "list" when used as a {% for %} source
    context: str | None = None


@dataclass(frozen=True)
class InvalidNameWarning:
    raw: str
    suggested_key: str
    count: int
    reason: str


@dataclass(frozen=True)
class DuplicateWarning:
    key: str
    count: int


@dataclass(frozen=True)
class DetectionResult:
    valid_fields: list[DetectedField] = field(default_factory=list)
    invalid_names: list[InvalidNameWarning] = field(default_factory=list)
    duplicates: list[DuplicateWarning] = field(default_factory=list)
    total_matches: int = 0
    unique_valid: int = 0
    parse_warning: str | None = None


def suggest_key(raw: str) -> str:
    """Normalize a malformed token into a suggested snake_case key."""
    return _suggest_key(raw)


def humanize_key(key: str) -> str:
    """'employee_name' -> 'Employee Name' (field_label for detected fields)."""
    return key_to_label(key)


def normalize_token(raw: str) -> str | None:
    """
    Resolve a {{ token }} body to its key, or None when it is malformed.
    'key', ' key ', 'key|default("")', 'obj.attr', 'r key' -> 'key'/'obj'.
    """
    body = raw.strip()
    body = re.sub(r"^(?:r|p|tr|tc)\s+(?=[A-Za-z_])", "", body)
    body = body.split("|", 1)[0].strip()
    body = re.split(r"[.\[(]", body, maxsplit=1)[0].strip()
    if VALID_KEY_PATTERN.match(body):
        return body
    return None


def _load(docx_bytes: bytes):
    tpl = DocxTemplate(BytesIO(docx_bytes))
    tpl.init_docx()
    document = tpl.docx
    assert document is not None, "docxtpl failed to initialize the document"
    return document


def extract_text_segments(docx_bytes: bytes) -> list[TextSegment]:
    """
    Every non-empty paragraph of the DOCX in canonical order (body incl.
    tables and text boxes, then headers/footers). Reused by cleaning (GET
    /content) and the AI context excerpt.
    """
    document = _load(docx_bytes)
    segments: list[TextSegment] = []
    for slot in walk_document(document).slots:
        if slot.text and slot.text.strip():
            segments.append(
                TextSegment(index=len(segments), location=slot.location, text=slot.text)
            )
    return segments


def get_template_variables(docx_bytes: bytes) -> tuple[set[str] | None, str | None]:
    """
    THE AUTHORITATIVE detector: docxtpl/Jinja2, the same engine that renders
    documents. Returns (variables, None) on success, (None, message) when
    malformed names make the template unparseable — never raises.
    """
    try:
        tpl = DocxTemplate(BytesIO(docx_bytes))
        variables = tpl.get_undeclared_template_variables()
        return set(variables), None
    except Exception as exc:  # jinja2.TemplateSyntaxError, docxtpl errors, ...
        return None, f"The template could not be parsed for document generation: {exc}"


def detect_placeholders(docx_bytes: bytes) -> DetectionResult:
    """Detect every {{placeholder}} in the DOCX. Read-only — never modifies the file."""
    document = _load(docx_bytes)
    dmap = walk_document(document)

    raw_info: dict[str, dict] = {}
    key_info: dict[str, dict] = {}
    loop_vars: set[str] = set()
    total_matches = 0
    section: str | None = None

    def see_key(key: str, slot, hint: str | None, count_match: bool) -> None:
        info = key_info.get(key)
        if info is None:
            in_margin = slot.location in ("header", "footer")
            info = key_info[key] = {
                "count": 0,
                "section": slot.location.capitalize() if in_margin else section,
                "location": slot.location,
                "hint": hint,
                "context": slot.text.strip()[:200],
            }
        if hint and not info["hint"]:
            info["hint"] = hint
        if count_match:
            info["count"] += 1

    for slot in dmap.slots:
        if slot.is_heading and slot.location not in ("header", "footer", "textbox"):
            section = slot.text.strip()[:100] or section
        tokens: list[tuple[int, str, str]] = []
        for match in PLACEHOLDER_PATTERN.finditer(slot.text):
            tokens.append((match.start(), "expr", match.group(1)))
        for match in STATEMENT_PATTERN.finditer(slot.text):
            tokens.append((match.start(), "stmt", match.group(1) or match.group(2)))
        for _, kind, body in sorted(tokens):
            if kind == "stmt":
                loop = _FOR.match(body)
                if loop:
                    loop_vars.add(loop.group(1))
                    if loop.group(2):
                        loop_vars.add(loop.group(2))
                    source = loop.group(3)
                    if VALID_KEY_PATTERN.match(source) and source not in loop_vars:
                        see_key(source, slot, "list", count_match=False)
                    continue
                condition = _IF.match(body)
                if condition and VALID_KEY_PATTERN.match(condition.group(1)):
                    name = condition.group(1)
                    if name not in loop_vars and name not in _JINJA_NAMES:
                        see_key(name, slot, None, count_match=False)
                continue
            total_matches += 1
            key = normalize_token(body)
            if key is None:
                info = raw_info.setdefault(body, {"count": 0})
                info["count"] += 1
                continue
            if key in loop_vars or key in _JINJA_NAMES:
                continue
            see_key(key, slot, None, count_match=True)

    invalid_names = [
        InvalidNameWarning(
            raw=raw,
            suggested_key=suggest_key(raw),
            count=info["count"],
            reason=_INVALID_NAME_REASON,
        )
        for raw, info in raw_info.items()
    ]

    variables, parse_warning = get_template_variables(docx_bytes)
    scanned = list(key_info)  # insertion order == first-seen document order
    if variables is not None:
        # Persist only keys docxtpl also sees (guaranteed to render); any
        # docxtpl-only variable the scan missed is appended after.
        persisted = [key for key in scanned if key in variables]
        extras = sorted(
            variable
            for variable in variables
            if variable not in key_info and VALID_KEY_PATTERN.match(variable)
        )
        persisted.extend(extras)
    else:
        persisted = scanned

    valid_fields = []
    for display_order, key in enumerate(persisted):
        info = key_info.get(key, {})
        valid_fields.append(
            DetectedField(
                key=key,
                display_order=display_order,
                section=info.get("section"),
                location=info.get("location"),
                type_hint=info.get("hint"),
                context=info.get("context"),
            )
        )

    duplicates = [
        DuplicateWarning(key=key, count=info["count"])
        for key, info in key_info.items()
        if info["count"] > 1
    ]

    return DetectionResult(
        valid_fields=valid_fields,
        invalid_names=invalid_names,
        duplicates=duplicates,
        total_matches=total_matches,
        unique_valid=len(valid_fields),
        parse_warning=parse_warning,
    )
