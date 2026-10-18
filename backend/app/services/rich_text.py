"""
Rich text for long-text (textarea) fields (V1.7 Phase 2).

The editor (Tiptap, frontend) sends its document as JSON. This module is the
security boundary for that JSON and the single definition of its plain-text
form. Pure: no database, no FastAPI.

- validate_rich_content(raw) -> normalized doc
    A WHITELIST: only the nodes and marks below, and only two attributes
    (link.href with http/https/mailto, orderedList.start). Anything else is
    rejected (unknown node / mark) or dropped (unknown key / attribute).
    These are exactly the features docxtpl RichText can render through a
    plain {{ field }} placeholder (see Prompts/V1.7-P2.md §2), so formatting
    never silently disappears between the editor and the document.
- to_plain_text(doc)
    The text the generated DOCX shows (frontend docToPlain must match):
    blocks joined by "\n"; hardBreak -> "\n"; bullet item "• text",
    ordered item "1. text" (respecting start), nested items indented by
    4 spaces per level with "◦ " for nested bullets; a list item's
    continuation paragraphs are indented one level deeper than its marker.
    Trailing whitespace is stripped.
- to_blocks(doc) / from_blocks(doc, texts)
    One entry per paragraph, in document order. Used to rewrite a rich field
    block by block with AI while keeping its paragraphs and list items.

Stored values never contain HTML: only the normalized JSON.
"""

import json
from collections.abc import Iterator
from typing import Any

ALLOWED_NODES = frozenset(
    {"doc", "paragraph", "text", "hardBreak", "bulletList", "orderedList", "listItem"}
)
ALLOWED_MARKS = frozenset({"bold", "italic", "underline", "strike", "link", "highlight"})
LINK_PROTOCOLS = ("http://", "https://", "mailto:")

MAX_JSON_BYTES = 50_000
MAX_TEXT_CHARS = 20_000
MAX_LIST_DEPTH = 3
MAX_LINK_LENGTH = 2048
MAX_ORDERED_START = 999

BULLET = "• "
NESTED_BULLET = "◦ "
INDENT = "    "

# Fixed mark order so equal formatting always serializes the same way.
_MARK_ORDER = ("bold", "italic", "underline", "strike", "highlight", "link")
_BLOCK_NODES = ("paragraph", "bulletList", "orderedList")
_LIST_NODES = ("bulletList", "orderedList")
_INLINE_NODES = ("text", "hardBreak")


class RichTextError(ValueError):
    """Invalid rich text; the message is safe to show to the user."""


# ── Validation ────────────────────────────────────────────────────


def _unsupported(name: Any) -> RichTextError:
    label = name if isinstance(name, str) and name else "unknown"
    return RichTextError(f"Unsupported formatting: {label[:40]}")


def _content(node: dict) -> list:
    content = node.get("content", [])
    if content is None:
        return []
    if not isinstance(content, list):
        raise RichTextError("Invalid rich text structure")
    return content


def _node_type(node: Any) -> str:
    if not isinstance(node, dict):
        raise RichTextError("Invalid rich text structure")
    node_type = node.get("type")
    if node_type not in ALLOWED_NODES:
        raise _unsupported(node_type)
    return node_type


def _normalize_href(raw: Any) -> str:
    if not isinstance(raw, str):
        raise RichTextError("A link needs an address")
    href = raw.strip()
    if not href:
        raise RichTextError("A link needs an address")
    if len(href) > MAX_LINK_LENGTH:
        raise RichTextError("A link address is too long")
    if any(ord(char) < 32 or char.isspace() for char in href):
        raise RichTextError("A link address must not contain spaces")
    if not href.lower().startswith(LINK_PROTOCOLS):
        raise RichTextError("Links must start with http://, https:// or mailto:")
    return href


def _normalize_marks(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RichTextError("Invalid rich text structure")
    marks: dict[str, dict] = {}
    for mark in raw:
        if not isinstance(mark, dict):
            raise RichTextError("Invalid rich text structure")
        mark_type = mark.get("type")
        if mark_type not in ALLOWED_MARKS:
            raise _unsupported(mark_type)
        if mark_type == "link":
            attrs = mark.get("attrs") if isinstance(mark.get("attrs"), dict) else {}
            marks["link"] = {"type": "link", "attrs": {"href": _normalize_href(attrs.get("href"))}}
        else:
            marks[mark_type] = {"type": mark_type}
    return [marks[name] for name in _MARK_ORDER if name in marks]


def _normalize_inline(node: Any) -> dict:
    node_type = _node_type(node)
    if node_type == "hardBreak":
        return {"type": "hardBreak"}
    if node_type != "text":
        raise RichTextError("Invalid rich text structure")
    text = node.get("text")
    if not isinstance(text, str) or text == "":
        raise RichTextError("Invalid rich text structure")
    normalized: dict = {"type": "text", "text": text}
    marks = _normalize_marks(node.get("marks"))
    if marks:
        normalized["marks"] = marks
    return normalized


def _normalize_paragraph(node: dict) -> dict:
    content = [_normalize_inline(child) for child in _content(node)]
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _normalize_list(node: dict, node_type: str, depth: int) -> dict:
    if depth > MAX_LIST_DEPTH:
        raise RichTextError(f"Lists can be nested at most {MAX_LIST_DEPTH} levels deep")
    items = []
    for child in _content(node):
        if _node_type(child) != "listItem":
            raise RichTextError("Invalid rich text structure")
        items.append(_normalize_list_item(child, depth))
    if not items:
        raise RichTextError("A list needs at least one item")
    normalized: dict = {"type": node_type, "content": items}
    if node_type == "orderedList":
        attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
        start = attrs.get("start", 1)
        if start is None:
            start = 1
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= MAX_ORDERED_START:
            raise RichTextError(f"A numbered list must start between 1 and {MAX_ORDERED_START}")
        if start != 1:
            normalized["attrs"] = {"start": start}
    return normalized


def _normalize_list_item(node: dict, depth: int) -> dict:
    content = []
    for index, child in enumerate(_content(node)):
        child_type = _node_type(child)
        if child_type == "paragraph":
            content.append(_normalize_paragraph(child))
        elif child_type in _LIST_NODES and index > 0:
            content.append(_normalize_list(child, child_type, depth + 1))
        else:
            raise RichTextError("Invalid rich text structure")
    if not content:
        raise RichTextError("Invalid rich text structure")
    return {"type": "listItem", "content": content}


def _normalize_block(node: Any) -> dict:
    node_type = _node_type(node)
    if node_type == "paragraph":
        return _normalize_paragraph(node)
    if node_type in _LIST_NODES:
        return _normalize_list(node, node_type, 1)
    raise RichTextError("Invalid rich text structure")


def validate_rich_content(raw: dict | str) -> dict:
    """
    Validate editor JSON against the whitelist and return a normalized copy.

    Raises RichTextError (user-safe message) for invalid JSON, an unsupported
    node or mark ("Unsupported formatting: heading"), a link that is not
    http(s)/mailto, lists nested deeper than MAX_LIST_DEPTH, more than
    MAX_JSON_BYTES of JSON or more than MAX_TEXT_CHARS of text.
    """
    if isinstance(raw, (str, bytes)):
        size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
        if size > MAX_JSON_BYTES:
            raise RichTextError("The formatted text is too large")
        try:
            raw = json.loads(raw)
        except (ValueError, RecursionError):
            raise RichTextError("The formatted text is not valid") from None
    elif isinstance(raw, dict):
        try:
            encoded = json.dumps(raw, ensure_ascii=False)
        except (TypeError, ValueError, RecursionError):
            raise RichTextError("The formatted text is not valid") from None
        if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
            raise RichTextError("The formatted text is too large")
    else:
        raise RichTextError("The formatted text is not valid")

    try:
        if _node_type(raw) != "doc":
            raise RichTextError("Invalid rich text structure")
        doc = {"type": "doc", "content": [_normalize_block(node) for node in _content(raw)]}
    except RecursionError:
        raise RichTextError("Invalid rich text structure") from None

    if len(to_plain_text(doc)) > MAX_TEXT_CHARS:
        raise RichTextError(f"The text must be at most {MAX_TEXT_CHARS:,} characters")
    return doc


# ── Plain text and blocks ─────────────────────────────────────────


def paragraph_text(paragraph: dict) -> str:
    """A paragraph's text; hard breaks become "\\n"."""
    parts = []
    for node in paragraph.get("content") or []:
        if node.get("type") == "hardBreak":
            parts.append("\n")
        else:
            parts.append(node.get("text", ""))
    return "".join(parts)


def iter_paragraphs(doc: dict) -> Iterator[tuple[dict, str, int, str]]:
    """
    Every paragraph of a (normalized) doc in document order, as
    (paragraph, kind, depth, prefix):

    - kind "p" (top level or a list item's continuation), "bullet" or
      "ordered" (the first paragraph of a list item)
    - depth: list nesting level (0 = not in a list)
    - prefix: the plain-text marker and indentation to put before the text
    """

    def walk_list(node: dict, depth: int) -> Iterator[tuple[dict, str, int, str]]:
        ordered = node["type"] == "orderedList"
        start = (node.get("attrs") or {}).get("start", 1)
        indent = INDENT * (depth - 1)
        for position, item in enumerate(node.get("content") or []):
            if ordered:
                kind, marker = "ordered", f"{start + position}. "
            else:
                kind, marker = "bullet", BULLET if depth == 1 else NESTED_BULLET
            first = True
            for child in item.get("content") or []:
                if child["type"] == "paragraph":
                    if first:
                        yield child, kind, depth, indent + marker
                        first = False
                    else:
                        yield child, "p", depth, INDENT * depth
                else:
                    yield from walk_list(child, depth + 1)

    for block in doc.get("content") or []:
        if block["type"] == "paragraph":
            yield block, "p", 0, ""
        else:
            yield from walk_list(block, 1)


def to_plain_text(doc: dict) -> str:
    """The plain-text projection (what the generated document shows)."""
    lines = [prefix + paragraph_text(paragraph) for paragraph, _, _, prefix in iter_paragraphs(doc)]
    return "\n".join(lines).rstrip()


def to_blocks(doc: dict) -> list[dict]:
    """[{"kind": "p"|"bullet"|"ordered", "depth": int, "text": str}] per paragraph."""
    return [
        {"kind": kind, "depth": depth, "text": paragraph_text(paragraph)}
        for paragraph, kind, depth, _ in iter_paragraphs(doc)
    ]


def _text_content(text: str) -> list[dict]:
    content: list[dict] = []
    for index, line in enumerate(text.split("\n")):
        if index:
            content.append({"type": "hardBreak"})
        if line:
            content.append({"type": "text", "text": line})
    return content


def from_blocks(doc: dict, rewritten_texts: list[str]) -> dict:
    """
    The doc with each paragraph's text replaced by rewritten_texts[i] (same
    order as to_blocks). Paragraphs and lists keep their structure; a
    rewritten paragraph loses its marks, an unchanged one keeps them.
    Raises RichTextError when the number of texts does not match.
    """
    doc = json.loads(json.dumps(doc))  # deep copy; never mutate the input
    paragraphs = [paragraph for paragraph, _, _, _ in iter_paragraphs(doc)]
    if len(paragraphs) != len(rewritten_texts):
        raise RichTextError("The rewritten text does not match the paragraphs")
    for paragraph, text in zip(paragraphs, rewritten_texts):
        if not isinstance(text, str):
            raise RichTextError("The rewritten text does not match the paragraphs")
        if text == paragraph_text(paragraph):
            continue
        content = _text_content(text.replace("\r\n", "\n").replace("\r", "\n"))
        if content:
            paragraph["content"] = content
        else:
            paragraph.pop("content", None)
    return doc


def parse_stored(rich_content: str | None) -> dict | None:
    """A stored rich_content column (JSON text) as a dict; None when absent or broken."""
    if not rich_content:
        return None
    try:
        value = json.loads(rich_content)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def dump(doc: dict) -> str:
    """Compact JSON text for storage."""
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
