"""
app.services.rich_text: the Tiptap JSON whitelist, its plain-text projection
and the block helpers used for AI rewrites (V1.7 Phase 2).

SHARED_DOC / SHARED_PLAIN are the shared test vector: the frontend's
docToPlain (frontend/tests/rich-model.test.ts) asserts the same string.
"""

import json
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.models.document_value import AI_ACTIONS
from app.schemas.ai import AI_TEXT_ACTIONS
from app.services.rich_text import (
    ALLOWED_MARKS,
    ALLOWED_NODES,
    MAX_JSON_BYTES,
    MAX_TEXT_CHARS,
    RichTextError,
    from_blocks,
    to_blocks,
    to_plain_text,
    validate_rich_content,
)


def text(value: str, *marks: dict) -> dict:
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def para(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)} if content else {"type": "paragraph"}


def item(*content: dict) -> dict:
    return {"type": "listItem", "content": list(content)}


def bullets(*items: dict) -> dict:
    return {"type": "bulletList", "content": list(items)}


def numbers(*items: dict, start: int | None = None) -> dict:
    node = {"type": "orderedList", "content": list(items)}
    if start is not None:
        node["attrs"] = {"start": start, "type": None}
    return node


def doc(*content: dict) -> dict:
    return {"type": "doc", "content": list(content)}


BOLD = {"type": "bold"}
ITALIC = {"type": "italic"}


def LINK(href: str) -> dict:
    return {"type": "link", "attrs": {"href": href, "target": "_blank", "rel": "noopener", "class": None}}


SHARED_DOC = doc(
    para(
        text("Intro with "),
        text("bold", BOLD),
        text(" and a "),
        text("link", LINK("https://example.com")),
        {"type": "hardBreak"},
        text("second line"),
    ),
    bullets(
        item(para(text("Apples")), bullets(item(para(text("Green"))))),
        item(para(text("Pears"))),
    ),
    numbers(
        item(
            para(text("Third", ITALIC, {"type": "highlight", "attrs": {"color": "#ff0"}})),
            para(text("more")),
        ),
        item(para(text("Fourth & <last>")), numbers(item(para(text("Sub"))))),
        start=3,
    ),
    para(),
)

SHARED_PLAIN = (
    "Intro with bold and a link\n"
    "second line\n"
    "• Apples\n"
    "    ◦ Green\n"
    "• Pears\n"
    "3. Third\n"
    "    more\n"
    "4. Fourth & <last>\n"
    "    1. Sub"
)


# ── Whitelist ─────────────────────────────────────────────────────


def test_whitelist_constants():
    assert ALLOWED_NODES == {
        "doc", "paragraph", "text", "hardBreak", "bulletList", "orderedList", "listItem",
    }
    assert ALLOWED_MARKS == {"bold", "italic", "underline", "strike", "link", "highlight"}
    assert AI_ACTIONS == AI_TEXT_ACTIONS


def test_shared_vector_normalizes_and_projects():
    normalized = validate_rich_content(SHARED_DOC)
    assert to_plain_text(normalized) == SHARED_PLAIN
    # Unknown attributes are dropped: link keeps only href, highlight none.
    intro = normalized["content"][0]["content"]
    assert intro[3]["marks"] == [{"type": "link", "attrs": {"href": "https://example.com"}}]
    third = normalized["content"][2]["content"][0]["content"][0]["content"][0]
    assert third["marks"] == [{"type": "italic"}, {"type": "highlight"}]
    assert normalized["content"][2]["attrs"] == {"start": 3}
    assert normalized["content"][3] == {"type": "paragraph"}


def test_accepts_json_text_and_is_idempotent():
    normalized = validate_rich_content(json.dumps(SHARED_DOC))
    assert validate_rich_content(normalized) == normalized


def test_marks_are_deduplicated_and_ordered():
    normalized = validate_rich_content(
        doc(para(text("x", {"type": "link", "attrs": {"href": "mailto:a@b.c"}}, BOLD,
                      {"type": "underline"}, BOLD, {"type": "strike"})))
    )
    marks = normalized["content"][0]["content"][0]["marks"]
    assert [m["type"] for m in marks] == ["bold", "underline", "strike", "link"]


@pytest.mark.parametrize(
    "bad, message",
    [
        (doc({"type": "heading", "attrs": {"level": 1}, "content": [text("T")]}), "Unsupported formatting: heading"),
        (doc({"type": "image", "attrs": {"src": "x.png"}}), "Unsupported formatting: image"),
        (doc({"type": "codeBlock", "content": [text("x")]}), "Unsupported formatting: codeBlock"),
        (doc({"type": "blockquote", "content": [para(text("x"))]}), "Unsupported formatting: blockquote"),
        (doc({"type": "table", "content": []}), "Unsupported formatting: table"),
        (doc(para(text("x", {"type": "code"}))), "Unsupported formatting: code"),
        (doc(para(text("x", {"type": "textStyle", "attrs": {"color": "red"}}))), "Unsupported formatting: textStyle"),
        (doc({"type": "taskList", "content": []}), "Unsupported formatting: taskList"),
        (doc(para({"type": "mention", "attrs": {"id": 1}})), "Unsupported formatting: mention"),
        (doc({"nope": 1}), "Unsupported formatting: unknown"),
    ],
)
def test_rejects_unsupported_nodes_and_marks(bad, message):
    with pytest.raises(RichTextError) as error:
        validate_rich_content(bad)
    assert str(error.value) == message


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " JavaScript:alert(1)",
        "data:text/html,<script>",
        "vbscript:x",
        "file:///etc/passwd",
        "//evil.example",
        "example.com",
        "",
        None,
        "https://exa mple.com",
        "https://example.com/\nx",
        "https://" + "a" * 3000,
    ],
)
def test_rejects_unsafe_links(href):
    with pytest.raises(RichTextError):
        validate_rich_content(doc(para(text("x", {"type": "link", "attrs": {"href": href}}))))


def test_accepts_safe_links_case_insensitive():
    for href in ("http://a.b", "HTTPS://A.B/x?q=1&r=2", "mailto:someone@example.com"):
        normalized = validate_rich_content(doc(para(text("x", {"type": "link", "attrs": {"href": f"  {href} "}}))))
        assert normalized["content"][0]["content"][0]["marks"][0]["attrs"]["href"] == href


@pytest.mark.parametrize(
    "bad",
    [
        [],
        "not json",
        "[1, 2]",
        {"type": "paragraph"},
        doc(text("loose text")),
        doc(para(para(text("x")))),
        doc(para(text(""))),
        doc(para({"type": "text"})),
        doc(para({"type": "text", "text": 5})),
        doc(bullets()),
        doc(bullets(para(text("x")))),
        doc(bullets(item())),
        doc(bullets(item(bullets(item(para(text("x"))))))),  # list item must start with a paragraph
        doc(bullets(item(text("x")))),
        {"type": "doc", "content": "x"},
        doc(para(text("x", "bold"))),
        doc(para({"type": "text", "text": "x", "marks": "bold"})),
        doc(numbers(item(para(text("x"))), start=0)),
        doc(numbers(item(para(text("x"))), start=1000)),
        {"type": "doc", "content": [{"type": "orderedList", "attrs": {"start": "2"}, "content": [item(para(text("x")))]}]},
        {"type": "doc", "content": [{"type": "orderedList", "attrs": {"start": True}, "content": [item(para(text("x")))]}]},
    ],
)
def test_rejects_invalid_structure(bad):
    with pytest.raises(RichTextError):
        validate_rich_content(bad)


def test_list_depth_limit():
    def nested(depth: int) -> dict:
        node = bullets(item(para(text(f"level {depth}"))))
        for level in range(depth - 1, 0, -1):
            node = bullets(item(para(text(f"level {level}")), node))
        return node

    assert to_plain_text(validate_rich_content(doc(nested(3)))) == (
        "• level 1\n    ◦ level 2\n        ◦ level 3"
    )
    with pytest.raises(RichTextError) as error:
        validate_rich_content(doc(nested(4)))
    assert "at most 3 levels" in str(error.value)


def test_size_limits():
    big = doc(para(text("x" * (MAX_JSON_BYTES + 10))))
    with pytest.raises(RichTextError, match="too large"):
        validate_rich_content(big)
    with pytest.raises(RichTextError, match="too large"):
        validate_rich_content(json.dumps(big))
    # Under the JSON limit but over the text limit (many short paragraphs
    # would exceed the JSON size first, so use one long text).
    long_text = doc(para(text("y" * (MAX_TEXT_CHARS + 1))))
    with pytest.raises(RichTextError, match="at most 20,000 characters"):
        validate_rich_content(long_text)
    assert to_plain_text(validate_rich_content(doc(para(text("y" * MAX_TEXT_CHARS))))) == "y" * MAX_TEXT_CHARS


def test_deep_nesting_does_not_crash():
    node: dict = bullets(item(para(text("x"))))
    for _ in range(3000):
        node = bullets(item(para(text("x")), node))
    with pytest.raises(RichTextError):
        validate_rich_content({"type": "doc", "content": [node]})
    with pytest.raises(RichTextError):
        validate_rich_content('{"type": "doc", "content": ' + "[" * 5000 + "]" * 5000 + "}")


def test_non_serializable_input_is_rejected():
    with pytest.raises(RichTextError):
        validate_rich_content({"type": "doc", "content": [{"type": "paragraph", "x": object()}]})
    with pytest.raises(RichTextError):
        validate_rich_content(42)  # type: ignore[arg-type]


def test_unknown_keys_dropped_and_hard_break_marks_ignored():
    normalized = validate_rich_content(
        {
            "type": "doc",
            "attrs": {"evil": 1},
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "center", "class": "x"},
                    "onclick": "alert(1)",
                    "content": [
                        {"type": "text", "text": "a", "style": "color:red"},
                        {"type": "hardBreak", "marks": [BOLD]},
                        text("b"),
                    ],
                }
            ],
        }
    )
    assert normalized == doc(para(text("a"), {"type": "hardBreak"}, text("b")))


# ── Plain text ────────────────────────────────────────────────────


def test_plain_text_cases():
    assert to_plain_text(validate_rich_content(doc())) == ""
    assert to_plain_text(validate_rich_content(doc(para()))) == ""
    assert to_plain_text(validate_rich_content(doc(para(text("a")), para(), para(text("b")), para()))) == "a\n\nb"
    assert to_plain_text(validate_rich_content(doc(para(text("emoji 🎉 & < > ✓"))))) == "emoji 🎉 & < > ✓"
    assert to_plain_text(validate_rich_content(doc(para(text("trailing   "))))) == "trailing"
    assert (
        to_plain_text(validate_rich_content(doc(numbers(item(para(text("a"))), item(para(text("b"))), start=9))))
        == "9. a\n10. b"
    )
    assert to_plain_text(validate_rich_content(doc(bullets(item(para(text("a"), {"type": "hardBreak"}, text("b"))))))) == "• a\nb"


# ── Blocks ────────────────────────────────────────────────────────


def test_to_blocks_shared_vector():
    blocks = to_blocks(validate_rich_content(SHARED_DOC))
    assert blocks == [
        {"kind": "p", "depth": 0, "text": "Intro with bold and a link\nsecond line"},
        {"kind": "bullet", "depth": 1, "text": "Apples"},
        {"kind": "bullet", "depth": 2, "text": "Green"},
        {"kind": "bullet", "depth": 1, "text": "Pears"},
        {"kind": "ordered", "depth": 1, "text": "Third"},
        {"kind": "p", "depth": 1, "text": "more"},
        {"kind": "ordered", "depth": 1, "text": "Fourth & <last>"},
        {"kind": "ordered", "depth": 2, "text": "Sub"},
        {"kind": "p", "depth": 0, "text": ""},
    ]


def test_from_blocks_keeps_structure_and_unchanged_marks():
    normalized = validate_rich_content(SHARED_DOC)
    texts = [block["text"] for block in to_blocks(normalized)]
    assert from_blocks(normalized, texts) == normalized  # nothing changed

    texts[0] = "Rewritten intro\nline two"
    texts[1] = "Red apples"
    texts[8] = ""
    rewritten = from_blocks(normalized, texts)
    assert validate_rich_content(rewritten) == rewritten
    assert rewritten["content"][0] == para(text("Rewritten intro"), {"type": "hardBreak"}, text("line two"))
    apples = rewritten["content"][1]["content"][0]["content"]
    assert apples[0] == para(text("Red apples"))
    assert apples[1]["type"] == "bulletList"  # nested list kept
    # Untouched blocks keep their marks.
    assert rewritten["content"][2]["content"][0]["content"][0] == normalized["content"][2]["content"][0]["content"][0]
    assert to_plain_text(rewritten).startswith("Rewritten intro\nline two\n• Red apples\n    ◦ Green")
    # The input is not mutated.
    assert to_plain_text(normalized) == SHARED_PLAIN


def test_from_blocks_length_mismatch():
    normalized = validate_rich_content(SHARED_DOC)
    with pytest.raises(RichTextError):
        from_blocks(normalized, ["only one"])
    with pytest.raises(RichTextError):
        from_blocks(normalized, [None] * 9)  # type: ignore[list-item]
