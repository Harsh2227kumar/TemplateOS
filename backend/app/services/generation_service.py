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

These rules live in context_value(); format_field_value() is the same rule
as display text, used by the preview page (V1.7) so it shows each value
exactly as the generated document does.

Rendering uses autoescape (so "&" and "<" are safe) and StrictUndefined: a
placeholder that is not one of the template's fields is a template problem
and is reported (TemplateRenderError -> HTTP 422) instead of silently
rendering blank.

Rich text (V1.7 Phase 2): a textarea value saved as Tiptap JSON is rendered
through the same plain `{{ field }}` placeholder as a docxtpl RichText
(rich_to_richtext): bold / italic / underline / strike runs, highlight as
shading, links as real hyperlinks, hard and paragraph breaks as line breaks,
list items as "• " / "1. " lines. Its text equals
rich_text.to_plain_text(doc), so the preview and the plain value match.
"""

import json
import logging
import re
from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING, Any

from docxtpl import DocxTemplate, RichText
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from markupsafe import escape as xml_escape

from app.services.rich_text import iter_paragraphs, to_plain_text

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


def context_value(field: "TemplateField", raw: str | None) -> "str | ListValue":
    """
    One field's docxtpl context value. The single formatting rule shared by
    generation (build_context) and the preview page (format_field_value).
    """
    raw = "" if raw is None else str(raw)
    if field.field_type == "list":
        return ListValue(parse_list_value(raw))
    if field.field_type == "date":
        return clean_text(format_date_value(raw))
    return clean_text(raw)


def format_field_value(field: "TemplateField", raw: str | None) -> str:
    """
    A field's value as display text, exactly as `{{ field_name }}` renders
    in the generated DOCX: ISO date -> DD-MM-YYYY (invalid dates unchanged),
    numbers / text unchanged, list -> non-blank items joined by a newline.
    None or blank -> "".
    """
    if raw is None or not str(raw).strip():
        return ""
    return str(context_value(field, raw))


def build_context(
    fields: list["TemplateField"], values: dict[str, str | None]
) -> dict[str, Any]:
    """
    The docxtpl context for a document: one entry per template field.

    `values` maps field_name -> stored value (missing / None = not filled).
    """
    return {
        field.field_name: context_value(field, values.get(field.field_name))
        for field in fields
    }


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


HIGHLIGHT_COLOR = "yellow"
LINK_COLOR = "0563C1"

# CT_RPr child order (ECMA-376), so merged run properties stay valid.
_RPR_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss "
            "imprint noProof snapToGrid vanish webHidden color spacing w kern position sz "
            "szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang "
            "eastAsianLayout specVanish oMath"
        ).split()
    )
}
_RPR_CHILD = re.compile(r"<w:(\w+)\b[^>]*?(?:/>|>.*?</w:\1>)", re.DOTALL)
# Properties a mark replaces: the template run's own value is dropped first.
_MARK_PROPS = {
    "bold": ("b", "bCs"),
    "italic": ("i", "iCs"),
    "underline": ("u",),
    "strike": ("strike", "dstrike"),
    "highlight": ("highlight", "shd"),
    "link": ("color", "u"),
}


def rich_segments(doc: dict) -> list[tuple[str, dict]]:
    """
    A normalized rich doc as (text, marks) runs in reading order, with "\\n"
    between paragraphs and for hard breaks, and the trailing whitespace
    removed exactly like rich_text.to_plain_text. `marks` maps a mark type
    to its attrs (link: {"href": ...}).
    """
    segments: list[tuple[str, dict]] = []
    for index, (paragraph, _kind, _depth, prefix) in enumerate(iter_paragraphs(doc)):
        if index:
            segments.append(("\n", {}))
        if prefix:
            segments.append((prefix, {}))
        for node in paragraph.get("content") or []:
            if node.get("type") == "hardBreak":
                segments.append(("\n", {}))
            else:
                marks = {mark["type"]: mark.get("attrs") or {} for mark in node.get("marks") or []}
                segments.append((node.get("text", ""), marks))
    # Strip trailing whitespace across runs (same result as str.rstrip()).
    while segments:
        text, marks = segments[-1]
        stripped = text.rstrip()
        if stripped:
            segments[-1] = (stripped, marks)
            break
        segments.pop()
    return segments


def _run_props(base_props: str, marks: dict) -> str:
    """The template run's properties with the marks applied, in schema order."""
    dropped = {prop for mark in marks for prop in _MARK_PROPS.get(mark, ())}
    children = [
        (match.group(1), match.group(0))
        for match in _RPR_CHILD.finditer(base_props)
        if match.group(1) not in dropped
    ]
    if "bold" in marks:
        children.append(("b", "<w:b/>"))
    if "italic" in marks:
        children.append(("i", "<w:i/>"))
    if "strike" in marks:
        children.append(("strike", "<w:strike/>"))
    if "highlight" in marks:
        children.append(("highlight", f'<w:highlight w:val="{HIGHLIGHT_COLOR}"/>'))
    if "link" in marks:
        children.append(("color", f'<w:color w:val="{LINK_COLOR}"/>'))
    if "underline" in marks or "link" in marks:
        children.append(("u", '<w:u w:val="single"/>'))
    children.sort(key=lambda child: _RPR_ORDER.get(child[0], len(_RPR_ORDER)))
    return "".join(xml for _, xml in children)


def _run_xml(text: str, props: str) -> str:
    """One run; "\\n" -> <w:br/>, "\\t" -> <w:tab/>, text XML-escaped."""
    parts = []
    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            parts.append("<w:br/>")
        for tab_index, chunk in enumerate(line.split("\t")):
            if tab_index:
                parts.append("<w:tab/>")
            if chunk:
                parts.append(f'<w:t xml:space="preserve">{xml_escape(chunk)}</w:t>')
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f"<w:r>{rpr}{''.join(parts)}</w:r>"


def rich_to_richtext(tpl: DocxTemplate, doc: dict, base_props: str = "") -> RichText:
    """
    The docxtpl RichText (run XML) for a normalized rich doc (see
    rich_segments). Every run starts from `base_props`, the formatting of
    the template run that held the placeholder (font, size, ...), with the
    marks applied: bold / italic / underline / strike, highlight (yellow),
    link (a real hyperlink, blue and underlined). Links need the template
    instance: build_url_id adds the relationship.
    """
    rich = RichText()
    for text, marks in rich_segments(doc):
        text = clean_text(text)
        if not text:
            continue
        run = _run_xml(text, _run_props(base_props, marks))
        href = marks.get("link", {}).get("href")
        if href:
            run = f'<w:hyperlink r:id="{tpl.build_url_id(href)}" w:history="1">{run}</w:hyperlink>'
        rich.xml += run
    return rich


# docxtpl's first two patch_xml steps: join "{{", "}}" split across runs and
# remove the XML tags inside a {{ ... }} tag, so a placeholder can be found.
_SPLIT_BRACES = re.compile(r"(?<={)(<[^>]*>)+(?=[\{%\#])|(?<=[%\}\#])(<[^>]*>)+(?=\})", re.DOTALL)
_JINJA_TAG = re.compile(r"{%(?:(?!%}).)*|{#(?:(?!#}).)*|{{(?:(?!}}).)*", re.DOTALL)
_TAGS_IN_JINJA = re.compile(r"</w:t>.*?(<w:t>|<w:t [^>]*>)", re.DOTALL)
_RUN_PROPS = re.compile(r"<w:rPr>(.*?)</w:rPr>", re.DOTALL)


class _RichDocxTemplate(DocxTemplate):
    """
    A DocxTemplate that renders rich fields through their plain
    `{{ field }}` placeholders.

    docxtpl only inserts run XML correctly for `{{r field }}` (which closes
    the surrounding run); a plain `{{ field }}` would put the runs inside
    the outer <w:t>, an invalid document. patch_xml therefore rewrites the
    simple placeholders of rich fields to `{{r field }}` and remembers the
    run properties of the placeholder's run, so the rich runs keep the
    template's font and size. Other uses of a rich field (filters, tests,
    loops) are left alone and get its plain text.
    """

    def __init__(self, template_file, rich_names):
        super().__init__(template_file)
        self.rich_names = tuple(rich_names)
        self.rich_run_props: dict[str, str] = {}

    def patch_xml(self, src_xml):
        src_xml = _SPLIT_BRACES.sub("", src_xml)
        src_xml = _JINJA_TAG.sub(lambda m: _TAGS_IN_JINJA.sub("", m.group(0)), src_xml)
        for name in self.rich_names:
            placeholder = re.compile(r"\{\{-?\s*" + re.escape(name) + r"\s*-?\}\}")
            match = placeholder.search(src_xml)
            if match is None:
                continue
            if name not in self.rich_run_props:
                run_start = max(src_xml.rfind("<w:r>", 0, match.start()), src_xml.rfind("<w:r ", 0, match.start()))
                props = _RUN_PROPS.search(src_xml, run_start, match.start()) if run_start >= 0 else None
                self.rich_run_props[name] = props.group(1) if props else ""
            src_xml = placeholder.sub("{{r " + name + " }}", src_xml)
        return super().patch_xml(src_xml)


class _RichValue:
    """
    Context value of a rich field: run XML where its `{{ field }}` was
    rewritten to `{{r field }}`, its plain text everywhere else (str(),
    filters, `{% if %}`).
    """

    def __init__(self, tpl: _RichDocxTemplate, name: str, doc: dict, plain: str):
        self.tpl, self.name, self.doc, self.plain = tpl, name, doc, plain

    def __str__(self) -> str:
        return self.plain

    def __bool__(self) -> bool:
        return bool(self.plain)

    def __html__(self) -> str:
        if self.name in self.tpl.rich_run_props:
            return rich_to_richtext(self.tpl, self.doc, self.tpl.rich_run_props[self.name]).xml
        return str(xml_escape(self.plain))


def render_docx(
    template_bytes: bytes,
    context: dict[str, Any],
    rich_values: dict[str, dict] | None = None,
) -> bytes:
    """
    Render the DOCX template with the context and return the new DOCX bytes.

    rich_values maps field_name -> normalized rich doc; those fields render
    with their formatting through `{{ field }}` (see _RichDocxTemplate). A
    rich value whose text is empty stays the context's "" so `{% if %}`
    tests behave like for plain values.

    Raises TemplateRenderError with a user-facing message on any docxtpl /
    Jinja failure (syntax error, undefined variable, broken XML).
    """
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    try:
        rich_values = {
            name: doc
            for name, doc in (rich_values or {}).items()
            if name in context and rich_segments(doc)
        }
        template = _RichDocxTemplate(BytesIO(template_bytes), rich_values)
        if rich_values:
            context = dict(context)
            for name, doc in rich_values.items():
                context[name] = _RichValue(template, name, doc, to_plain_text(doc))
        template.render(context, jinja_env=environment, autoescape=True)
        output = BytesIO()
        template.save(output)
    except Exception as exc:  # docxtpl/jinja2/lxml raise many types
        logger.info("Template render failed: %s", exc)
        raise TemplateRenderError(_describe_error(exc)) from exc
    return output.getvalue()
