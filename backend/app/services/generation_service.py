"""
DOCX generation service (V1.6 Phase 1).

Renders a template's fill-ready DOCX (the processed copy, see
docx_cleaner.get_renderable_path) with a document's saved values via docxtpl.

Context rules (build_context):
- Every template field is in the context, so an unfilled or optional field
  renders as an empty string, never "None".
- list  -> a Python list (stored as a JSON-array string), so the cleaned
           templates' `{%p for item in agenda_items %}` loops iterate items.
           Blank items are dropped. Printed directly as `{{ agenda_items }}`
           it renders one item per line (ListValue.__str__).
- date  -> ISO dates (YYYY-MM-DD) are shown as DD-MM-YYYY (format_date_value);
           anything else is passed through unchanged.
- number and all other types -> the string exactly as stored.
- "\r\n" is normalised to "\n" (docxtpl turns "\n" into a line break and
  "\t" into a tab); other control characters are removed because they are
  invalid in XML or would inject paragraph/page breaks.

Rendering uses autoescape (so "&" and "<" are safe) and StrictUndefined: a
placeholder that is not one of the template's fields is a template problem
and is reported (TemplateRenderError -> HTTP 422) instead of silently
rendering blank.
"""

import json
import logging
import re
from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING, Any

from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

if TYPE_CHECKING:
    from app.models.template_field import TemplateField

logger = logging.getLogger(__name__)

# Display format for ISO date values: 2026-10-13 -> 13-10-2026.
DATE_DISPLAY_FORMAT = "%d-%m-%Y"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Keep \t and \n; drop every other C0 control character (and DEL).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class TemplateRenderError(Exception):
    """The template could not be rendered; the message is user-facing."""


class ListValue(list):
    """A list that prints one item per line when used as `{{ key }}`."""

    def __str__(self) -> str:
        return "\n".join(str(item) for item in self)


def format_date_value(value: str) -> str:
    """
    Show an ISO date (YYYY-MM-DD, as the date input stores it) as
    DD-MM-YYYY. Any other string, including an invalid date like
    2026-02-30, is returned unchanged so nothing the user typed is lost.
    """
    text = value.strip()
    if not _ISO_DATE.match(text):
        return value
    try:
        return date.fromisoformat(text).strftime(DATE_DISPLAY_FORMAT)
    except ValueError:
        return value


def clean_text(value: str) -> str:
    """Normalise newlines and strip control characters invalid in DOCX text."""
    return _CONTROL_CHARS.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))


def parse_list_value(value: str) -> list[str]:
    """
    A stored list value (JSON array of strings) as a list of non-blank items.
    A blank value is an empty list; a non-JSON value becomes one item.
    """
    if not value or not value.strip():
        return []
    try:
        items = json.loads(value)
    except ValueError:
        items = [value]
    if not isinstance(items, list):
        items = [items]
    result = []
    for item in items:
        if item is None:
            continue
        text = clean_text(str(item))
        if text.strip():
            result.append(text)
    return result


def build_context(
    fields: list["TemplateField"], values: dict[str, str | None]
) -> dict[str, Any]:
    """
    The docxtpl context for a document: one entry per template field.

    `values` maps field_name -> stored value (missing / None = not filled).
    """
    context: dict[str, Any] = {}
    for field in fields:
        raw = values.get(field.field_name)
        raw = "" if raw is None else str(raw)
        if field.field_type == "list":
            context[field.field_name] = ListValue(parse_list_value(raw))
        elif field.field_type == "date":
            context[field.field_name] = clean_text(format_date_value(raw))
        else:
            context[field.field_name] = clean_text(raw)
    return context


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, UndefinedError):
        match = re.search(r"'([^']+)' is undefined", str(exc))
        if match:
            return (
                f"The template uses '{match.group(1)}', which is not one of its "
                "fields (or is used outside its loop). Add the field or re-clean "
                "the template."
            )
        return f"The template refers to an undefined value: {exc}"
    if isinstance(exc, TemplateSyntaxError):
        snippet = " ".join(
            part.strip() for part in getattr(exc, "docx_context", []) or [] if part.strip()
        )
        message = f"The template has a syntax error: {exc.message}"
        if snippet:
            message += f" (near: {snippet[:120]})"
        return message
    return f"The template could not be rendered: {exc}"


def render_docx(template_bytes: bytes, context: dict[str, Any]) -> bytes:
    """
    Render the DOCX template with the context and return the new DOCX bytes.

    Raises TemplateRenderError with a user-facing message on any docxtpl /
    Jinja failure (syntax error, undefined variable, broken XML).
    """
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    try:
        template = DocxTemplate(BytesIO(template_bytes))
        template.render(context, jinja_env=environment, autoescape=True)
        output = BytesIO()
        template.save(output)
    except Exception as exc:  # docxtpl/jinja2/lxml raise many types
        logger.info("Template render failed: %s", exc)
        raise TemplateRenderError(_describe_error(exc)) from exc
    return output.getvalue()
