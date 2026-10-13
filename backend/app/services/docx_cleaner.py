"""
DOCX cleaning service (V1.3 Phase 2 — template pipeline).

Pure replacement engine — NO database access. Turns owner-confirmed spots
of the ORIGINAL DOCX into {{ placeholders }} and returns a NEW processed
DOCX. The caller's bytes are never mutated: the engine works on a copy.

Two kinds of replacement are supported (both may be mixed in one request):

1. Text replacements (the original contract): every occurrence of
   `sample_text` in body paragraphs, table cells (nested), text boxes and
   headers/footers becomes `{{ key }}`.
2. Anchored replacements (from GET /clean-suggestions): an exact spot
   addressed by `paragraph_id` (docx_walker pid) and character offsets:
     - replace  text[start:end] -> {{ key }}
     - insert   {{ key }} at `start` (empty values: "Date:" -> "Date: {{ date }}",
                empty table cells)
     - list     the item paragraphs `paragraph_ids` -> a docxtpl loop:
                {%p for item in key %} / {{ item }} / {%p endfor %}

Formatting: only the characters being replaced are edited. Text split
across several runs is replaced in place; the placeholder takes the
formatting of the run where the replaced text starts, and every other run
(bold labels, tabs, drawings, text boxes) is left untouched.

Hard rules (MD/features.md §4):
- Manual confirmation only — exactly the replacements the owner confirmed.
- The original file is preserved; this module never writes to storage.
- Placeholder keys must pass VALID_KEY_PATTERN; invalid keys are skipped
  and reported, never injected into the document.
- Existing {{ }} / {% %} tags are never edited by a text replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal, overload

from docxtpl import DocxTemplate

from app.services.docx_parser import VALID_KEY_PATTERN
from app.services.docx_walker import (
    DocumentMap,
    iter_all_paragraph_elements,
    make_paragraph_like,
    paragraph_text,
    protected_spans,
    replace_span,
    set_paragraph_text,
    walk_document,
)


@dataclass(frozen=True)
class ReplacementSpec:
    """One confirmed conversion: sample_text (or an anchored spot) -> key."""

    sample_text: str
    placeholder_key: str
    location_hint: str | None = None
    segment_index: int | None = None
    paragraph_id: int | None = None
    start: int | None = None
    end: int | None = None
    action: str | None = None  # replace | insert | list (None = text replace)
    paragraph_ids: tuple[int, ...] = field(default_factory=tuple)

    @property
    def anchored(self) -> bool:
        return self.paragraph_id is not None and self.action is not None


@dataclass(frozen=True)
class ReplacementResult:
    """Per-replacement outcome (mirrors schemas.cleaning.ReplacementResult)."""

    placeholder_key: str
    sample_text: str
    occurrences: int = 0
    matched: bool = False
    reason: str | None = None


def placeholder_text(key: str) -> str:
    return "{{ " + key + " }}"


def _normalize_specs(replacements) -> list[tuple[ReplacementSpec, bool]]:
    """Accept ReplacementSpec objects, Pydantic models, or raw dicts; validate keys."""
    specs: list[tuple[ReplacementSpec, bool]] = []
    for item in replacements:
        if isinstance(item, ReplacementSpec):
            spec = item
        else:
            if isinstance(item, dict):
                data = dict(item)
                anchor = data.get("anchor")
            else:  # Pydantic model (schemas.cleaning.PlaceholderReplacement)
                data = {
                    "sample_text": item.sample_text,
                    "placeholder_key": item.placeholder_key,
                    "location_hint": getattr(item, "location_hint", None),
                    "segment_index": getattr(item, "segment_index", None),
                }
                anchor = getattr(item, "anchor", None)
            if anchor is not None and not isinstance(anchor, dict):
                anchor = anchor.model_dump()
            spec = ReplacementSpec(
                sample_text=data.get("sample_text") or "",
                placeholder_key=data["placeholder_key"],
                location_hint=data.get("location_hint"),
                segment_index=data.get("segment_index"),
                paragraph_id=anchor.get("paragraph_id") if anchor else None,
                start=anchor.get("start") if anchor else None,
                end=anchor.get("end") if anchor else None,
                action=(anchor.get("action") or "replace") if anchor else None,
                paragraph_ids=tuple(anchor.get("paragraph_ids") or ()) if anchor else (),
            )
        is_valid = bool(VALID_KEY_PATTERN.match(spec.placeholder_key))
        specs.append((spec, is_valid))
    return specs


# ── text replacement (original contract) ────────────────────────────


def _find_all(text: str, find: str) -> list[int]:
    positions = []
    start = text.find(find)
    while start != -1:
        positions.append(start)
        start = text.find(find, start + len(find))
    return positions


def _replace_everywhere(dmap: DocumentMap, find: str, repl: str) -> int:
    """Replace every occurrence of `find` outside existing tags; count primaries."""
    if not find:
        return 0
    occurrences = 0
    for slot, element in iter_all_paragraph_elements(dmap):
        if element.getparent() is None:
            continue  # removed by a list loop
        text = paragraph_text(element)
        guarded = protected_spans(text)
        hits = [
            index
            for index in _find_all(text, find)
            if not any(s < index + len(find) and index < e for s, e in guarded)
        ]
        # Right-to-left so earlier offsets stay valid while editing.
        count = 0
        for index in reversed(hits):
            if replace_span(element, index, index + len(find), repl):
                count += 1
        if element is slot.p:
            occurrences += count
    return occurrences


# ── anchored replacement ─────────────────────────────────────────────


@dataclass
class _Edit:
    index: int  # position in the request
    spec: ReplacementSpec
    start: int
    end: int
    text: str


def _is_token(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{{") and stripped.endswith("}}")


def _resolve_anchor(dmap: DocumentMap, spec: ReplacementSpec) -> tuple[int, int] | str:
    """Validate an anchor against its paragraph; returns (start, end) or a reason."""
    slot = dmap.slot(spec.paragraph_id)  # type: ignore[arg-type]
    if slot is None:
        return "anchor_not_found"
    text = slot.text
    guarded = protected_spans(text)
    start = spec.start if spec.start is not None else 0
    end = spec.end if spec.end is not None else start
    if spec.action == "insert":
        if start > len(text):
            return "anchor_mismatch"
        if any(s < start < e for s, e in guarded):
            return "inside_existing_placeholder"
        return start, start
    candidates: list[tuple[int, int]] = []
    if 0 <= start < end <= len(text) and (
        not spec.sample_text or text[start:end] == spec.sample_text
    ):
        candidates.append((start, end))
    elif spec.sample_text and spec.sample_text in text:
        # The paragraph shifted slightly (e.g. re-saved file): fall back to
        # the sample text inside the SAME paragraph.
        found = text.find(spec.sample_text)
        candidates.append((found, found + len(spec.sample_text)))
    if not candidates:
        return "anchor_mismatch"
    start, end = candidates[0]
    if any(s < end and start < e for s, e in guarded) and not _is_token(text[start:end]):
        return "inside_existing_placeholder"
    return start, end


def _insert_text(text: str, position: int, key: str) -> str:
    token = placeholder_text(key)
    before = text[position - 1] if position > 0 else ""
    after = text[position] if position < len(text) else ""
    if before and not before.isspace():
        token = " " + token
    if after and not after.isspace() and after not in ".,;:)":
        token = token + " "
    return token


def _apply_list(dmap: DocumentMap, spec: ReplacementSpec) -> str | None:
    """Turn consecutive list paragraphs into a docxtpl paragraph loop."""
    pids = list(spec.paragraph_ids) or [spec.paragraph_id]
    slots = [dmap.slot(pid) for pid in pids]
    if not slots or any(slot is None for slot in slots):
        return "anchor_not_found"
    for slot in slots:
        if slot.p.getparent() is None:
            return "overlaps_another_replacement"
        if protected_spans(slot.text):
            return "inside_existing_placeholder"
    first = slots[0]
    loop_var = "entry" if spec.placeholder_key == "item" else "item"
    item_token = "{{ " + loop_var + " }}"
    prefix = first.manual_list_prefix.strip() if not first.has_numbering else ""
    if prefix and prefix[0].isdigit():
        item_text = "{{ loop.index }}" + prefix.lstrip("0123456789") + " " + item_token
    elif prefix and not prefix[0].isalnum() and prefix[0] != "(":
        item_text = prefix + " " + item_token
    else:
        item_text = item_token
    open_p = make_paragraph_like(
        first.p,
        "{%p for " + loop_var + " in " + spec.placeholder_key + " %}",
        keep_numbering=False,
    )
    close_p = make_paragraph_like(first.p, "{%p endfor %}", keep_numbering=False)
    first.p.addprevious(open_p)
    set_paragraph_text(first.p, item_text)
    first.p.addnext(close_p)
    for slot in slots[1:]:
        parent = slot.p.getparent()
        if parent is not None:
            parent.remove(slot.p)
    return None


def _apply(docx_bytes: bytes, replacements) -> tuple[bytes, list[ReplacementResult]]:
    """Core engine: validate keys, apply anchored then text edits, return (bytes, results)."""
    tpl = DocxTemplate(BytesIO(docx_bytes))
    tpl.init_docx()
    document = tpl.docx
    assert document is not None, "docxtpl failed to initialize the document"
    dmap = walk_document(document)

    specs = _normalize_specs(replacements)
    results: list[ReplacementResult | None] = [None] * len(specs)

    def done(index: int, spec: ReplacementSpec, occurrences: int, reason: str | None) -> None:
        results[index] = ReplacementResult(
            placeholder_key=spec.placeholder_key,
            sample_text=spec.sample_text,
            occurrences=occurrences,
            matched=occurrences > 0,
            reason=None if occurrences > 0 else reason,
        )

    # 1. Anchored span edits, grouped per paragraph. Offsets are relative to
    #    the ORIGINAL text, so each paragraph is edited right-to-left.
    edits_by_pid: dict[int, list[_Edit]] = {}
    list_specs: list[tuple[int, ReplacementSpec]] = []
    list_pids: set[int] = set()
    for index, (spec, is_valid) in enumerate(specs):
        if not is_valid:
            done(index, spec, 0, "invalid_key")
            continue
        if not spec.anchored:
            continue
        if spec.action == "list":
            pids = set(spec.paragraph_ids or (spec.paragraph_id,))
            if pids & list_pids:
                done(index, spec, 0, "overlaps_another_replacement")
                continue
            list_specs.append((index, spec))
            list_pids.update(pids)
            continue
        resolved = _resolve_anchor(dmap, spec)
        if isinstance(resolved, str):
            done(index, spec, 0, resolved)
            continue
        start, end = resolved
        slot = dmap.slot(spec.paragraph_id)  # type: ignore[arg-type]
        new_text = (
            _insert_text(slot.text, start, spec.placeholder_key)
            if start == end
            else placeholder_text(spec.placeholder_key)
        )
        edits_by_pid.setdefault(spec.paragraph_id, []).append(  # type: ignore[arg-type]
            _Edit(index=index, spec=spec, start=start, end=end, text=new_text)
        )

    for pid, edits in edits_by_pid.items():
        slot = dmap.slot(pid)
        if pid in list_pids:
            for edit in edits:
                done(edit.index, edit.spec, 0, "overlaps_another_replacement")
            continue
        accepted: list[_Edit] = []
        for edit in sorted(edits, key=lambda e: (e.start, e.end)):
            clash = any(
                (edit.start < other.end and other.start < edit.end)
                or (edit.start == edit.end and other.start <= edit.start <= other.end)
                or (other.start == other.end and edit.start <= other.start <= edit.end)
                for other in accepted
            )
            if clash:
                done(edit.index, edit.spec, 0, "overlaps_another_replacement")
            else:
                accepted.append(edit)
        twins = [twin for twin in slot.twins if paragraph_text(twin) == slot.text]
        for edit in sorted(accepted, key=lambda e: e.start, reverse=True):
            ok = replace_span(slot.p, edit.start, edit.end, edit.text)
            if ok:
                for twin in twins:
                    replace_span(twin, edit.start, edit.end, edit.text)
            done(edit.index, edit.spec, 1 if ok else 0, None if ok else "anchor_mismatch")

    # 2. List loops (whole paragraphs; after span edits so pids stay valid).
    for index, spec in list_specs:
        reason = _apply_list(dmap, spec)
        done(index, spec, 0 if reason else 1, reason)

    # 3. Text replacements (original contract) — longest sample first so a
    #    short sample cannot break a longer one that contains it.
    text_specs = [
        (index, spec)
        for index, (spec, is_valid) in enumerate(specs)
        if is_valid and not spec.anchored
    ]
    text_specs.sort(key=lambda pair: len(pair[1].sample_text), reverse=True)
    for index, spec in text_specs:
        occurrences = _replace_everywhere(
            dmap, spec.sample_text, placeholder_text(spec.placeholder_key)
        )
        done(index, spec, occurrences, "sample_text_not_found")

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue(), [result for result in results if result is not None]


@overload
def apply_replacements(
    docx_bytes: bytes, replacements, return_unmatched: Literal[False] = False
) -> bytes: ...


@overload
def apply_replacements(
    docx_bytes: bytes, replacements, return_unmatched: Literal[True]
) -> tuple[bytes, list[str]]: ...


def apply_replacements(docx_bytes: bytes, replacements, return_unmatched: bool = False):
    """
    Apply confirmed replacements to a COPY of the DOCX and return the processed bytes.

    Returns processed_bytes, or (processed_bytes, unmatched_sample_texts) when
    return_unmatched is True. The endpoint uses apply_replacements_with_results().
    """
    processed, results = _apply(docx_bytes, replacements)
    if return_unmatched:
        unmatched = [r.sample_text for r in results if not r.matched]
        return processed, unmatched
    return processed


def apply_replacements_with_results(docx_bytes: bytes, replacements):
    """(processed_bytes, list[ReplacementResult]) — results in REQUEST order."""
    return _apply(docx_bytes, replacements)


def check_renderable(docx_bytes: bytes) -> str | None:
    """None when docxtpl can parse the template, else the parse error message."""
    try:
        DocxTemplate(BytesIO(docx_bytes)).get_undeclared_template_variables()
        return None
    except Exception as exc:  # jinja2.TemplateSyntaxError and friends
        return str(exc)


def get_renderable_path(template) -> str:
    """
    Generation-source contract (V1.6): the fill-ready file is the processed
    copy when it exists, else the original. Returns '' when neither is set.
    """
    return template.processed_file_path or template.original_file_path or ""


def fix_placeholder_tokens(
    docx_bytes: bytes, fixes: list[tuple[str, str]]
) -> tuple[bytes, list[int]]:
    """
    Rename malformed tokens: every {{ raw }} (any inner spacing) becomes
    {{ key }} in a copy of the DOCX. Returns (bytes, count per fix).
    """
    import re

    tpl = DocxTemplate(BytesIO(docx_bytes))
    tpl.init_docx()
    document = tpl.docx
    assert document is not None, "docxtpl failed to initialize the document"
    dmap = walk_document(document)
    counts = [0] * len(fixes)
    for number, (raw, key) in enumerate(fixes):
        if not VALID_KEY_PATTERN.match(key):
            continue
        pattern = re.compile(r"\{\{\s*" + re.escape(raw.strip()) + r"\s*\}\}")
        for slot, element in iter_all_paragraph_elements(dmap):
            text = paragraph_text(element)
            matches = list(pattern.finditer(text))
            for match in reversed(matches):
                if replace_span(element, match.start(), match.end(), placeholder_text(key)):
                    if element is slot.p:
                        counts[number] += 1
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue(), counts
