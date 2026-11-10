"""
Automatic cleaning suggestions (template pipeline).

Pure analysis — NO database access, never modifies the document. Scans an
UNCLEANED DOCX for spots that should become {{ placeholders }} and proposes
each one with a snake_case key, a Title Case label, a field type, a
confidence score and a human-readable reason. The owner reviews and accepts;
POST /clean applies the accepted ones through each suggestion's `anchor`.

Rules (highest priority first; a span claimed by one rule is never reused):

    fixes       malformed existing tokens: {{Meeting Title}} -> {{ meeting_title }}
    lists       numbered/bulleted item blocks -> a docxtpl loop over a list field
    tables      label cell + empty/filled value cell (row-wise) and
                header row + empty/filled data cells (column-wise), merged-cell aware
    blanks      "Name: ______", "Venue .......", inline "held on ------"
    brackets    [Name], <Date>, {Department}, «Field», (Signature)
    empty       "Date:" / "Date :" / "Name:<tabs>" with no value
    filled      "Date: 12/03/2024", "Venue: Seminar Hall"
    dummy       sample filler such as "Committee Name A", "XYZ"
    detected    dates / times / emails / phones / "by <Name>" / signatory names
                in running text (lower confidence)

Existing {{ }} / {% %} spans are protected: nothing is proposed inside them.
Repeated labels collapse onto one key; different values under one label get
a context prefix (meeting_date) or a numeric suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from docxtpl import DocxTemplate

from app.services.docx_walker import (
    DocumentMap,
    ParagraphSlot,
    TableInfo,
    protected_spans,
    walk_document,
)
from app.services.field_inference import (
    DATE_VALUE,
    EMAIL_VALUE,
    NUMBER_VALUE,
    PHONE_VALUE,
    TIME_VALUE,
    VALID_KEY,
    infer_field_meta,
    is_phone,
    label_to_key,
    normalize_label,
    suggest_key,
)

HIGH_CONFIDENCE = 0.8

GROUPS = {
    "fix_invalid": "fixes",
    "list": "lists",
    "table_cell": "tables",
    "table_value": "tables",
    "leader": "blanks",
    "inline_blank": "blanks",
    "bracket": "brackets",
    "empty_value": "empty_values",
    "filled_value": "filled_values",
    "dummy_text": "filled_values",
    "detected_value": "detected_values",
}

# Labels that are almost always form fields.
_VOCAB = {
    "name", "date", "time", "venue", "place", "signature", "sign", "subject",
    "ref no", "reference no", "roll no", "registration no", "reg no", "class",
    "department", "dept", "designation", "email", "e mail", "email id",
    "phone", "mobile", "mobile no", "phone no", "contact", "contact no",
    "address", "to", "from", "title", "topic", "duration", "semester", "year",
    "division", "branch", "course", "program", "programme", "event",
    "organized by", "organised by", "prepared by", "verified by",
    "approved by", "submitted by", "submitted to", "chaired by", "chairperson",
    "coordinator", "convener", "convenor", "guest", "speaker", "resource person",
    "amount", "total", "marks", "remarks", "purpose", "reason", "dob",
    "date of birth", "gender", "age", "enrollment no", "prn", "student name",
    "faculty name", "faculty", "hod", "principal", "director", "dean",
    "meeting title", "title of the meeting", "agenda", "attendees", "members",
    "members present", "present", "absent", "minutes", "action items",
    "target date", "deadline", "status", "outcome", "attendance", "batch",
    "academic year", "session", "employee id", "employee name", "id",
    "certificate no", "serial no", "sr no", "no", "place of event",
}
_LABEL_CHARS = re.compile(r"^[A-Za-z][A-Za-z0-9 .&/()'’\-#,]*$")
_LEADER = re.compile(r"_{3,}|\.{4,}|…{2,}|-{4,}|–{3,}|—{2,}|(?:_\s){3,}_?")
_CHUNK_SPLIT = re.compile(r"\t+| {3,}")
_PAIR = re.compile(r"^(?P<label>[^:：\n]{1,48}?)\s*[:：]\s*(?P<value>.*?)\s*$")
_BRACKETS = (
    (re.compile(r"«\s*([^«»\n]{1,48}?)\s*»"), 0.95, "«…» merge-field marker"),
    (re.compile(r"\[\s*([^\[\]\n]{1,48}?)\s*\]"), 0.9, "[…] fill-in hint"),
    (re.compile(r"<\s*([^<>\n]{1,48}?)\s*>"), 0.9, "<…> fill-in hint"),
    (re.compile(r"(?<!\{)\{\s*([^{}\n%#]{1,48}?)\s*\}(?!\})"), 0.9, "{…} fill-in hint"),
    (re.compile(r"\(\s*([^()\n]{1,32}?)\s*\)"), 0.65, "(…) fill-in hint"),
)
_PAREN_REJECT = {
    "am/pm", "am", "pm", "if any", "optional", "s", "es", "approx", "tick",
    "yes/no", "please tick", "in words", "in figures", "etc", "i", "ii", "iii",
}
_DUMMY_TEXT = re.compile(
    r"^(?:abc|xyz|xxx+|x+|lorem ipsum.*|sample(?: text)?|tbd|n/?a|"
    r"item\s*\d+|point\s*\d+|name\s*[a-z]?|text|dummy.*|placeholder)$",
    re.IGNORECASE,
)
_DUMMY_PHRASE = re.compile(
    r"\b(?:[A-Z][a-z]+\s+)+(?:Name(?:\s+[A-Z])?|Incharge\s+Name)\b(?=\s*(?:,|$))"
)
_SUBJECT_NOUNS = (
    "meeting", "event", "workshop", "seminar", "webinar", "exam", "examination",
    "lecture", "session", "programme", "program", "visit", "function",
    "conference", "competition", "interview", "training", "orientation",
    "ceremony", "celebration", "drive", "hackathon", "fest",
)
_LIST_NOUNS = (
    "points", "items", "decisions", "members", "attendees", "participants",
    "tasks", "actions", "topics", "resolutions", "suggestions", "objectives",
    "outcomes", "recommendations", "observations",
)
_ROLE_WORDS = re.compile(
    r"\b(director|dean|principal|head|hod|incharge|in-charge|coordinator|"
    r"convener|convenor|secretary|president|chairperson|chairman|professor|"
    r"faculty|registrar|officer|manager|committee|member|teacher|mentor|"
    r"advisor|adviser|guide|warden|librarian|controller|chief)\b",
    re.IGNORECASE,
)
_HONORIFIC_NAME = re.compile(
    r"\b(?:Dr|Prof|Mr|Mrs|Ms|Shri|Smt)\.?\s+(?:[A-Z]\.\s*)*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}"
)
_BY_NAME = re.compile(
    r"\b(?P<verb>[A-Za-z]+)\s+by\s+(?P<name>(?:(?:Dr|Prof|Mr|Mrs|Ms|Shri|Smt)\.?\s+)?"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
)
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "at", "is", "was", "were", "be",
    "will", "by", "for", "and", "with", "as", "from", "this", "that", "are",
    "has", "have", "held", "following", "dear", "your", "our", "its", "into",
}


@dataclass
class Suggestion:
    kind: str
    base_key: str
    label: str | None
    confidence: float
    reason: str
    pid: int
    start: int
    end: int
    action: str  # replace | insert | list
    sample_text: str
    value: str | None = None
    location: str = "body"
    paragraph_ids: list[int] = field(default_factory=list)
    allow_list: bool = True
    forced_type: str | None = None
    subject: str | None = None
    # filled in by finalize()
    key: str = ""
    field_label: str = ""
    field_type: str = "text"
    validation_rule: str | None = None
    is_required: bool = True
    ai_enabled: bool = False
    section: str | None = None
    example_value: str | None = None
    context_before: str = ""
    context_after: str = ""
    paragraph_text: str = ""
    shared_with: int = 1
    loop_text: str | None = None
    section_hint: str | None = None

    @property
    def group(self) -> str:
        return GROUPS.get(self.kind, "detected_values")

    @property
    def id(self) -> str:
        return f"{self.pid}:{self.start}:{self.end}:{self.kind}"


@dataclass
class SuggestionReport:
    suggestions: list[Suggestion]
    existing_keys: list[str]
    paragraph_count: int


# ── helpers ──────────────────────────────────────────────────────────


def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", normalize_label(label).lower().replace(".", " ")).strip()


def _norm_vocab(label: str) -> str:
    return re.sub(r"\s+", " ", _norm(label))


def is_label_like(text: str, max_words: int = 6) -> bool:
    label = normalize_label(text)
    if not label or len(label) > 48:
        return False
    if not _LABEL_CHARS.match(label):
        return False
    words = label.split()
    if len(words) > max_words:
        return False
    if label.endswith((".", ",")) and not re.search(r"\b(no|ref|sr)\.$", label, re.I):
        return False
    letters = sum(ch.isalpha() for ch in label)
    if letters < 2 or letters < len(label.replace(" ", "")) * 0.5:
        return False
    if DATE_VALUE.search(label) or EMAIL_VALUE.search(label):
        return False
    return True


_SENTENCE_WORDS = {
    "was", "were", "is", "are", "will", "have", "has", "had", "following",
    "be", "been", "shall", "should", "would", "please", "we", "you", "i",
}


def _clean_label_end(label: str) -> bool:
    """A label does not end in a dangling article/preposition ('A meeting of the')."""
    words = re.findall(r"[A-Za-z]+", label.lower())
    dangling = {"the", "a", "an", "of", "and", "or", "with", "for", "is", "was"}
    return bool(words) and words[-1] not in dangling and not (
        set(words) & _SENTENCE_WORDS
    ) and not (len(words) > 2 and words[0] in ("a", "an", "the"))


def _is_intro_label(text: str) -> bool:
    return is_label_like(text, max_words=5) and _clean_label_end(text)


def _in_vocab(label: str) -> bool:
    return _norm_vocab(label) in _VOCAB


def _overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    for s, e in spans:
        if start == end:
            if s < start < e:
                return True
        elif start < e and s < end:
            return True
    return False


def _context_words(text: str, limit: int = 4) -> list[str]:
    words = re.findall(r"[A-Za-z]+", text)
    return words[-limit:]


def _subject_noun(text: str) -> str | None:
    """The most specific event noun in the text (priority order, not position)."""
    lowered = text.lower()
    for noun in _SUBJECT_NOUNS:
        if re.search(rf"\b{noun}\b", lowered):
            return "program" if noun == "programme" else noun
    return None


class _Analyzer:
    def __init__(self, dmap: DocumentMap):
        self.dmap = dmap
        self.slots = dmap.slots
        self.claims: dict[int, list[tuple[int, int]]] = {}
        self.consumed: set[int] = set()  # whole paragraphs handled
        self.out: list[Suggestion] = []
        self.sections = self._sections()
        for slot in self.slots:
            spans = protected_spans(slot.text)
            if spans:
                self.claims[slot.pid] = list(spans)

    # -- infrastructure --

    def _sections(self) -> dict[int, str | None]:
        sections: dict[int, str | None] = {}
        current: str | None = None
        for slot in self.slots:
            if slot.location in ("header", "footer"):
                sections[slot.pid] = slot.location.capitalize()
                continue
            if slot.is_heading and slot.location != "textbox":
                current = normalize_label(slot.stripped)[:100] or current
            sections[slot.pid] = current
        return sections

    def claim(self, pid: int, start: int, end: int) -> bool:
        spans = self.claims.setdefault(pid, [])
        if pid in self.consumed or _overlaps(spans, start, end):
            return False
        spans.append((start, end) if end > start else (start, start))
        return True

    def add(self, suggestion: Suggestion) -> bool:
        if suggestion.action != "list" and not self.claim(
            suggestion.pid, suggestion.start, suggestion.end
        ):
            return False
        if not suggestion.base_key or not VALID_KEY.match(suggestion.base_key):
            suggestion.base_key = suggest_key(suggestion.base_key or "field")
        self.out.append(suggestion)
        return True

    def next_non_empty(self, pid: int, distance: int = 4) -> ParagraphSlot | None:
        slot = self.slots[pid]
        for other in self.slots[pid + 1 : pid + 1 + distance]:
            if other.location != slot.location or other.container_id != slot.container_id:
                return None
            if other.stripped:
                return other
        return None

    def prev_non_empty(self, pid: int, distance: int = 3) -> ParagraphSlot | None:
        slot = self.slots[pid]
        for other in reversed(self.slots[max(0, pid - distance) : pid]):
            if other.location != slot.location or other.container_id != slot.container_id:
                return None
            if other.stripped:
                return other
        return None

    # -- rules --

    def run(self) -> list[Suggestion]:
        self.rule_fix_invalid()
        self.rule_lists()
        self.rule_tables()
        for slot in self.slots:
            if slot.pid in self.consumed or not slot.stripped:
                continue
            if slot.stripped.startswith(("{%", "{#")):
                continue
            self.rule_paragraph(slot)
        for slot in self.slots:
            if slot.pid in self.consumed or not slot.stripped:
                continue
            self.rule_detected_values(slot)
        return self.out

    def rule_fix_invalid(self) -> None:
        for slot in self.slots:
            for match in re.finditer(r"\{\{\s*([^{}]+?)\s*\}\}", slot.text):
                raw = match.group(1)
                key = _normalize_token(raw)
                if key is not None:
                    continue
                fixed = suggest_key(raw)
                self.out.append(
                    Suggestion(
                        kind="fix_invalid",
                        base_key=fixed,
                        label=raw,
                        confidence=0.9,
                        reason=f"'{{{{{raw}}}}}' is not a valid placeholder name; rename it to '{fixed}'",
                        pid=slot.pid,
                        start=match.start(),
                        end=match.end(),
                        action="replace",
                        sample_text=match.group(0),
                        location=slot.location,
                    )
                )

    def rule_lists(self) -> None:
        index = 0
        slots = self.slots
        while index < len(slots):
            slot = slots[index]
            if not slot.is_list_item or slot.location == "textbox" or slot.pid in self.consumed:
                index += 1
                continue
            block = [slot]
            cursor = index + 1
            while cursor < len(slots):
                candidate = slots[cursor]
                if (
                    candidate.is_list_item
                    and candidate.container_id == slot.container_id
                    and candidate.location == slot.location
                    and candidate.has_numbering == slot.has_numbering
                    and candidate.p.getprevious() is block[-1].p
                ):
                    block.append(candidate)
                    cursor += 1
                else:
                    break
            index = cursor
            if len(block) < 2:
                continue
            if any(protected_spans(item.text) for item in block):
                continue
            self._list_suggestion(block)

    def _list_suggestion(self, block: list[ParagraphSlot]) -> None:
        items = [
            item.stripped[len(item.manual_list_prefix.strip()):].strip()
            if item.manual_list_prefix
            else item.stripped
            for item in block
        ]
        # Keep a long, fixed closing item (e.g. "Any other point with the
        # permission of the chair.") as static text.
        if len(block) >= 3 and len(items[-1]) > 40 and all(len(i) <= 30 for i in items[:-1]):
            block = block[:-1]
            items = items[:-1]
        if len(block) < 2:
            return
        intro = self.prev_non_empty(block[0].pid, distance=3)
        section = self.sections.get(block[0].pid)
        key, label = None, None
        if intro is not None and _is_intro_label(intro.stripped) and not intro.is_list_item:
            label = normalize_label(intro.stripped)
            key = label_to_key(label)
            self.consumed.add(intro.pid)
        else:
            sentence = intro.stripped.lower() if intro is not None else ""
            noun = next((n for n in _LIST_NOUNS if re.search(rf"\b{n}\b", sentence)), None)
            base = label_to_key(section) if section else ""
            if noun and base and noun not in base:
                key = f"{base}_{noun}"
            elif noun:
                key = noun
            elif base:
                key = f"{base}_items"
            else:
                key = "items"
        if not key.endswith(tuple(_LIST_NOUNS)) and key.split("_")[-1] not in (
            "agenda", "attendees", "members", "participants", "list", "names",
        ):
            if not key.endswith("s"):
                key = f"{key}_items"
        dummy = all(not text or _DUMMY_TEXT.match(text) or len(text) <= 3 for text in items)
        manual = bool(block[0].manual_list_prefix) and not block[0].has_numbering
        confidence = 0.88 if dummy else 0.72
        reason = (
            f"{len(block)} {'numbered' if manual else 'list'} items"
            + (" with sample/empty text" if dummy else "")
            + " -> one list field rendered as a loop"
        )
        example_items = [text for text in items if text and not _DUMMY_TEXT.match(text)]
        suggestion = Suggestion(
            kind="list",
            base_key=key,
            label=label,
            confidence=confidence,
            reason=reason,
            pid=block[0].pid,
            start=0,
            end=len(block[0].text),
            action="list",
            sample_text="\n".join(item.text for item in block),
            value=", ".join(example_items)[:255] or None,
            location=block[0].location,
            paragraph_ids=[item.pid for item in block],
            forced_type="list",
        )
        if self.add(suggestion):
            for item in block:
                self.consumed.add(item.pid)

    def rule_tables(self) -> None:
        for table in self.dmap.tables:
            self._table(table)

    def _table(self, table: TableInfo) -> None:
        rows = [row for row in table.rows if row]
        if not rows:
            return
        header = rows[0]
        header_like = (
            len(rows) >= 2
            and len(header) >= 2
            and all(cell.text and is_label_like(cell.text, max_words=5) for cell in header)
        )
        data_rows = rows[1:]
        column_mode = header_like and any(
            not cell.text or not is_label_like(cell.text)
            for row in data_rows
            for cell in row
            if not cell.vmerge_continue
        )
        if column_mode:
            columns = {cell.col: cell for cell in header}
            usable_rows = [row for row in data_rows][:10]
            multi = len(usable_rows) > 1
            for row_number, row in enumerate(usable_rows, start=1):
                for cell in row:
                    head = columns.get(cell.col)
                    if head is None or cell.vmerge_continue or not cell.pids:
                        continue
                    if any(protected_spans(self.slots[pid].text) for pid in cell.pids):
                        continue
                    label = normalize_label(head.text)
                    base = label_to_key(label)
                    key = f"{base}_{row_number}" if multi else base
                    display = f"{label} {row_number}" if multi else label
                    self._cell_value(
                        cell,
                        key,
                        display,
                        f"column '{label}' (row {row_number})",
                        empty_conf=0.78,
                        filled_conf=0.55,
                    )
                    for pid in cell.pids:
                        self.consumed.add(pid)
            for cell in header:
                for pid in cell.pids:
                    self.consumed.add(pid)
            return

        for row in rows:
            cells = [cell for cell in row if not cell.vmerge_continue]
            for position, cell in enumerate(cells[:-1]):
                target = cells[position + 1]
                if not cell.text or not is_label_like(cell.text, max_words=6):
                    continue
                if target.text and is_label_like(target.text) and (
                    _in_vocab(target.text) or target.text.rstrip().endswith(":")
                ):
                    continue  # two labels side by side (a header pair)
                label = normalize_label(cell.text)
                if not label or "{{" in cell.text:
                    continue
                vocab = _in_vocab(label)
                created = self._cell_value(
                    target,
                    label_to_key(label),
                    label,
                    f"table label '{label}'",
                    empty_conf=0.9 if vocab else 0.82,
                    filled_conf=0.78 if vocab else 0.68,
                )
                if created:
                    for pid in cell.pids + target.pids:
                        self.consumed.add(pid)

    def _cell_value(self, cell, key, label, where, empty_conf, filled_conf) -> bool:
        if not cell.pids:
            return False
        first = self.slots[cell.pids[0]]
        if not cell.text:
            return self.add(
                Suggestion(
                    kind="table_cell",
                    base_key=key,
                    label=label,
                    confidence=empty_conf,
                    reason=f"Empty table cell next to {where}",
                    pid=first.pid,
                    start=0,
                    end=0,
                    action="insert",
                    sample_text="",
                    location=first.location,
                    allow_list=False,
                )
            )
        text_slots = [self.slots[pid] for pid in cell.pids if self.slots[pid].stripped]
        if len(text_slots) != 1:
            return False
        slot = text_slots[0]
        stripped = slot.stripped
        leader = _LEADER.fullmatch(stripped)
        start = slot.text.index(stripped)
        end = start + len(stripped)
        if leader:
            return self.add(
                Suggestion(
                    kind="table_cell",
                    base_key=key,
                    label=label,
                    confidence=empty_conf,
                    reason=f"Blank line in the table cell for {where}",
                    pid=slot.pid,
                    start=start,
                    end=end,
                    action="replace",
                    sample_text=stripped,
                    location=slot.location,
                    allow_list=False,
                )
            )
        if len(stripped) > 200:
            return False
        return self.add(
            Suggestion(
                kind="table_value",
                base_key=key,
                label=label,
                confidence=filled_conf,
                reason=f"Sample value in the table cell for {where}",
                pid=slot.pid,
                start=start,
                end=end,
                action="replace",
                sample_text=stripped,
                value=stripped,
                location=slot.location,
                allow_list=False,
            )
        )

    # -- paragraph rules --

    def rule_paragraph(self, slot: ParagraphSlot) -> None:
        text = slot.text
        chunks = []
        position = 0
        for piece in _CHUNK_SPLIT.split(text):
            index = text.find(piece, position)
            if piece.strip():
                chunks.append((index, piece))
            position = index + len(piece)
        for number, (offset, chunk) in enumerate(chunks):
            last_chunk = number == len(chunks) - 1
            previous = chunks[number - 1][1] if number > 0 else None
            self._chunk(slot, offset, chunk, last_chunk, previous)

    def _chunk(self, slot, offset, chunk, last_chunk, previous_chunk) -> None:
        # 1. leaders / blanks
        leaders = list(_LEADER.finditer(chunk))
        if leaders:
            self._leaders(slot, offset, chunk, leaders, previous_chunk)
        # 2. brackets
        self._brackets(slot, offset, chunk)
        if leaders:
            return
        # 3. label: value
        pair = _PAIR.match(chunk)
        if pair and is_label_like(pair.group("label")) and not pair.group("value").startswith("//"):
            label = normalize_label(pair.group("label"))
            value = pair.group("value")
            value_start = offset + pair.start("value")
            colon_end = offset + chunk.index(":" if ":" in chunk[: pair.end("label") + 3] else "：", pair.end("label")) + 1
            if not value:
                self._empty_label(slot, label, colon_end, last_chunk)
            else:
                self._filled(slot, label, value, value_start)
            return
        # 4. label without colon followed by whitespace ("Name\t\t\t")
        stripped = chunk.strip()
        if _in_vocab(stripped) and not slot.is_heading and (
            not last_chunk or slot.text.rstrip("\t ") != slot.text
        ):
            insert_at = offset + chunk.index(stripped) + len(stripped)
            self.add(
                Suggestion(
                    kind="empty_value",
                    base_key=label_to_key(stripped),
                    label=stripped,
                    confidence=0.7,
                    reason=f"Label '{stripped}' followed only by spacing",
                    pid=slot.pid,
                    start=insert_at,
                    end=insert_at,
                    action="insert",
                    sample_text="",
                    location=slot.location,
                )
            )
            return
        # 5. sample filler ("Committee Name A, SIT Nagpur")
        self._dummy(slot, offset, chunk)

    def _leaders(self, slot, offset, chunk, leaders, previous_chunk) -> None:
        for number, match in enumerate(leaders):
            start = offset + match.start()
            end = offset + match.end()
            prefix = chunk[: match.start()]
            suffix = chunk[match.end():]
            label_text = re.sub(r"[\s:：\-–]+$", "", prefix).strip()
            if number == 0 and label_text and is_label_like(label_text) and _clean_label_end(label_text):
                label = normalize_label(label_text)
                self.add(
                    Suggestion(
                        kind="leader",
                        base_key=label_to_key(label),
                        label=label,
                        confidence=0.95 if _in_vocab(label) else 0.9,
                        reason=f"Blank line after the label '{label}'",
                        pid=slot.pid,
                        start=start,
                        end=end,
                        action="replace",
                        sample_text=match.group(0),
                        location=slot.location,
                    )
                )
                continue
            if number == 0 and not label_text:
                label = None
                if previous_chunk and is_label_like(previous_chunk):
                    label = normalize_label(previous_chunk)
                elif not slot.text[: start].strip():
                    before = self.prev_non_empty(slot.pid, 1)
                    after = self.next_non_empty(slot.pid, 2)
                    if after is not None and is_label_like(after.stripped):
                        label = normalize_label(after.stripped)
                    elif before is not None and is_label_like(before.stripped) and before.stripped.endswith(":"):
                        label = normalize_label(before.stripped)
                if label:
                    self.add(
                        Suggestion(
                            kind="leader",
                            base_key=label_to_key(label),
                            label=label,
                            confidence=0.8,
                            reason=f"Blank line for '{label}'",
                            pid=slot.pid,
                            start=start,
                            end=end,
                            action="replace",
                            sample_text=match.group(0),
                            location=slot.location,
                        )
                    )
                    continue
            key, label, ftype = _inline_blank_key(slot.text[: start], slot.text[end:])
            self.add(
                Suggestion(
                    kind="inline_blank",
                    base_key=key,
                    label=label,
                    confidence=0.72,
                    reason="Blank to fill in running text"
                    + (f" (after '{' '.join(_context_words(slot.text[:start], 3))}')" if slot.text[:start].strip() else ""),
                    pid=slot.pid,
                    start=start,
                    end=end,
                    action="replace",
                    sample_text=match.group(0),
                    location=slot.location,
                    forced_type=ftype,
                    subject=_subject_noun(slot.text[:start]),
                )
            )

    def _brackets(self, slot, offset, chunk) -> None:
        for pattern, confidence, why in _BRACKETS:
            for match in pattern.finditer(chunk):
                inner = match.group(1).strip()
                if not inner or not is_label_like(inner, max_words=5):
                    continue
                lowered = _norm_vocab(inner)
                if lowered in _PAREN_REJECT:
                    continue
                conf = confidence
                if pattern.pattern.startswith(r"\("):
                    if inner.islower() and not _in_vocab(inner):
                        continue
                    if not (_in_vocab(inner) or inner.istitle() or inner.isupper()):
                        continue
                    if _in_vocab(inner) or re.search(r"(?i)sign|name|date", inner):
                        conf = 0.8
                start = offset + match.start()
                end = offset + match.end()
                self.add(
                    Suggestion(
                        kind="bracket",
                        base_key=label_to_key(inner),
                        label=normalize_label(inner),
                        confidence=conf,
                        reason=f"{why}: '{match.group(0)}'",
                        pid=slot.pid,
                        start=start,
                        end=end,
                        action="replace",
                        sample_text=match.group(0),
                        location=slot.location,
                    )
                )

    def _empty_label(self, slot, label, colon_end, last_chunk) -> None:
        following = self.next_non_empty(slot.pid)
        if following is not None and following.is_list_item and following.pid in self.consumed:
            return  # the list rule already turned the items into a loop
        vocab = _in_vocab(label)
        confidence = 0.9 if vocab else 0.8
        reason = f"Label '{label}' has no value"
        kind = "empty_value"
        if following is not None and len(following.stripped) > 60 and not vocab and last_chunk:
            # "Discussion:" followed by a paragraph: more likely a heading.
            confidence = 0.4
            reason = f"'{label}:' looks like a heading followed by text; make it a field only if the text below changes"
        insert_at = colon_end
        if insert_at < len(slot.text) and slot.text[insert_at] == " ":
            insert_at += 1
        self.add(
            Suggestion(
                kind=kind,
                base_key=label_to_key(label),
                label=label,
                confidence=confidence,
                reason=reason,
                pid=slot.pid,
                start=insert_at,
                end=insert_at,
                action="insert",
                sample_text="",
                location=slot.location,
            )
        )

    def _filled(self, slot, label, value, value_start) -> None:
        value = value.rstrip()
        if not value or len(value) > 200:
            return
        if _LEADER.search(value) or "{{" in value:
            return
        typed = bool(
            DATE_VALUE.fullmatch(value)
            or TIME_VALUE.fullmatch(value)
            or EMAIL_VALUE.fullmatch(value)
            or (is_phone(value) and PHONE_VALUE.fullmatch(value))
            or NUMBER_VALUE.match(value)
        )
        if len(label.split()) > 4 and not typed:
            return  # prose with a colon ("The details are as follows: ...")
        vocab = _in_vocab(label)
        confidence = 0.86 if (vocab or typed) else 0.72
        if len(value) > 80:
            confidence = min(confidence, 0.6)
        self.add(
            Suggestion(
                kind="filled_value",
                base_key=label_to_key(label),
                label=label,
                confidence=confidence,
                reason=f"Sample value '{value[:40]}' after the label '{label}'",
                pid=slot.pid,
                start=value_start,
                end=value_start + len(value),
                action="replace",
                sample_text=value,
                value=value,
                location=slot.location,
            )
        )

    def _dummy(self, slot, offset, chunk) -> None:
        stripped = chunk.strip()
        start = offset + chunk.index(stripped)
        if _DUMMY_TEXT.fullmatch(stripped) and not slot.is_heading:
            following = self.next_non_empty(slot.pid, 2)
            label = None
            if following is not None and _ROLE_WORDS.search(following.stripped):
                label = following.stripped.split(",")[0]
            key = label_to_key(label) + "_name" if label else "sample_text"
            self.add(
                Suggestion(
                    kind="dummy_text",
                    base_key=key,
                    label=None,
                    confidence=0.6,
                    reason=f"'{stripped}' looks like sample filler text",
                    pid=slot.pid,
                    start=start,
                    end=start + len(stripped),
                    action="replace",
                    sample_text=stripped,
                    value=None,
                    location=slot.location,
                )
            )
            return
        for match in _DUMMY_PHRASE.finditer(chunk):
            phrase = match.group(0)
            words = [w for w in phrase.split() if len(w) > 1 or w.islower()]
            label = " ".join(words)
            self.add(
                Suggestion(
                    kind="dummy_text",
                    base_key=label_to_key(label),
                    label=label,
                    confidence=0.62,
                    reason=f"'{phrase}' is a generic name placeholder",
                    pid=slot.pid,
                    start=offset + match.start(),
                    end=offset + match.end(),
                    action="replace",
                    sample_text=phrase,
                    value=phrase,
                    location=slot.location,
                )
            )

    # -- low-confidence values in running text --

    def rule_detected_values(self, slot: ParagraphSlot) -> None:
        text = slot.text
        subject = _subject_noun(text)
        for match in EMAIL_VALUE.finditer(text):
            self._detected(slot, match.start(), match.end(), "email", "Email", 0.7, "Email address in the text")
        for match in DATE_VALUE.finditer(text):
            words = [w.lower() for w in _context_words(text[: match.start()], 3)]
            base = f"{subject}_date" if subject else "date"
            if words and words[-1] in ("dated", "date", "on") and subject is None:
                base = "date"
            self._detected(slot, match.start(), match.end(), base, None, 0.6, "Date in the text", subject)
        for match in TIME_VALUE.finditer(text):
            if not re.search(r"[ap]\.?m|hrs|hours|:", match.group(0), re.I):
                continue
            base = f"{subject}_time" if subject else "time"
            self._detected(slot, match.start(), match.end(), base, None, 0.55, "Time in the text", subject)
        for match in PHONE_VALUE.finditer(text):
            if not is_phone(match.group(0)):
                continue
            self._detected(slot, match.start(), match.end(), "phone", "Phone", 0.6, "Phone number in the text")
        for match in _BY_NAME.finditer(text):
            verb = match.group("verb").lower()
            if verb in _STOP:
                continue
            start = match.start("name")
            self._detected(
                slot, start, match.end("name"), f"{verb}_by", f"{verb.capitalize()} by",
                0.6, f"Person named after '{verb} by'",
            )
        stripped = slot.stripped
        name_like = _HONORIFIC_NAME.fullmatch(stripped) or (
            slot.location == "textbox"
            and re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}", stripped)
            and not _ROLE_WORDS.search(stripped)
        )
        if name_like:
            following = self.next_non_empty(slot.pid, 2)
            if following is not None and (_ROLE_WORDS.search(following.stripped) or "," in following.stripped):
                role = following.stripped.split(",")[0]
                role_words = [w for w in re.findall(r"[A-Za-z]+", role) if w.lower() not in ("name",) and len(w) > 1]
                role_key = label_to_key(" ".join(role_words[:3]) or "signatory")
                if role_key.endswith("committee"):
                    role_key += "_member"
                start = slot.text.index(stripped)
                self._detected(
                    slot, start, start + len(stripped), f"{role_key}_name", None, 0.58,
                    f"Name above the designation '{role.strip()}'",
                    section_hint="Signatures",
                )
        else:
            for match in _HONORIFIC_NAME.finditer(text):
                self._detected(
                    slot, match.start(), match.end(), "person_name", "Person Name", 0.5,
                    "Person's name in the text",
                )

    def _detected(self, slot, start, end, base, label, confidence, reason, subject=None, section_hint=None) -> None:
        value = slot.text[start:end]
        self.add(
            Suggestion(
                section_hint=section_hint,
                kind="detected_value",
                base_key=base,
                label=label,
                confidence=confidence,
                reason=f"{reason}: '{value}'",
                pid=slot.pid,
                start=start,
                end=end,
                action="replace",
                sample_text=value,
                value=value,
                location=slot.location,
                subject=subject,
            )
        )


_CHAIR_VERBS = {"held", "chaired", "conducted", "presided", "headed", "led"}


def _inline_blank_key(before: str, after: str) -> tuple[str, str | None, str | None]:
    """Name a blank inside a sentence from its neighbours."""
    words = [w.lower() for w in _context_words(before, 5)]
    after_words = [w.lower() for w in re.findall(r"[A-Za-z/.]+", after)[:2]]
    subject = _subject_noun(before)
    prefix = f"{subject}_" if subject else ""
    last = words[-1] if words else ""
    last_two = words[-2:]
    if after_words and after_words[0].strip(".") in ("am/pm", "am", "pm", "a.m", "p.m", "hrs", "hours"):
        return f"{prefix}time", None, None
    if last in ("on", "dated", "date"):
        return f"{prefix}date", None, "date"
    honorific = re.search(r"\b(prof|dr|mr|mrs|ms|shri|smt)\.?\s*$", before, re.I)
    if honorific or last == "by":
        by_index = max((i for i, w in enumerate(words) if w == "by"), default=None)
        verb = words[by_index - 1] if by_index else None
        if verb in _CHAIR_VERBS:
            return "chairperson_name", None, None
        if verb and verb not in _STOP:
            return f"{verb}_by", None, None
        return f"{prefix}person_name", None, None
    if last_two == ["of", "the"] or last == "of":
        owner = words[-3] if last == "the" and len(words) >= 3 else (words[-2] if len(words) >= 2 else "")
        if owner in ("meeting", "committee"):
            return "committee_name", None, None
        if owner and owner not in _STOP:
            return f"{owner}_of", None, None
    if last_two in (["at", "the"], ["in", "the"]) or last in ("venue", "at", "in"):
        if last == "at" and re.match(r"\s*\d", after):
            return f"{prefix}time", None, None
        return f"{prefix}venue", None, None
    content = [w for w in words if w not in _STOP]
    if content:
        return "_".join(content[-2:]), None, None
    return "blank", None, None


def _normalize_token(raw: str) -> str | None:
    """Return the key for a valid {{ token }} body, else None."""
    body = raw.strip()
    body = re.sub(r"^(?:r|p|tr|tc)\s+", "", body)
    body = body.split("|", 1)[0].strip()
    body = body.split(".", 1)[0].strip()
    body = body.split("[", 1)[0].strip()
    if VALID_KEY.match(body):
        return body
    return None


# ── finalize: keys, dedupe, metadata ─────────────────────────────────


def _finalize(analyzer: _Analyzer, existing_keys: set[str]) -> list[Suggestion]:
    suggestions = sorted(analyzer.out, key=lambda s: (s.pid, s.start))
    by_key: dict[str, list[Suggestion]] = {}
    by_value: dict[str, str] = {}
    slots = analyzer.slots

    def signature(s: Suggestion) -> str:
        return re.sub(r"\s+", " ", (s.value or "").strip().lower())

    for suggestion in suggestions:
        base = suggestion.base_key
        sig = signature(suggestion)
        if suggestion.kind == "fix_invalid":
            suggestion.key = base
            by_key.setdefault(base, []).append(suggestion)
            continue
        if sig and len(sig) >= 4 and sig in by_value:
            suggestion.key = by_value[sig]
            by_key.setdefault(suggestion.key, []).append(suggestion)
            continue
        key = base
        users = by_key.get(key, [])
        compatible = (
            not users
            or all(signature(u) == sig for u in users)
            or (not sig and all(not signature(u) for u in users) and suggestion.kind not in ("table_cell", "inline_blank", "detected_value", "dummy_text"))
        )
        if not compatible:
            subject = suggestion.subject or _subject_noun(
                " ".join(slots[pid].text for pid in range(max(0, suggestion.pid - 3), suggestion.pid + 1))
            )
            candidate = f"{subject}_{key}" if subject and not key.startswith(subject) else None
            if candidate and candidate not in by_key:
                key = candidate
            else:
                number = 2
                while f"{key}_{number}" in by_key:
                    number += 1
                key = f"{key}_{number}"
        suggestion.key = key[:100]
        by_key.setdefault(suggestion.key, []).append(suggestion)
        if sig and len(sig) >= 4:
            by_value.setdefault(sig, suggestion.key)

    for suggestion in suggestions:
        slot = slots[suggestion.pid]
        section = suggestion.section_hint or analyzer.sections.get(suggestion.pid)
        meta = infer_field_meta(
            suggestion.key,
            label=suggestion.label,
            value=suggestion.value,
            section=section,
            field_type=suggestion.forced_type,
            allow_list=suggestion.allow_list,
        )
        suggestion.field_label = meta.field_label
        suggestion.field_type = meta.field_type
        suggestion.validation_rule = meta.validation_rule
        suggestion.is_required = meta.is_required
        suggestion.ai_enabled = meta.ai_enabled
        suggestion.section = meta.section
        suggestion.example_value = None if suggestion.kind == "dummy_text" else meta.example_value
        suggestion.shared_with = len(by_key.get(suggestion.key, []))
        if suggestion.key in existing_keys and suggestion.kind != "fix_invalid":
            suggestion.reason += f" (reuses the existing '{suggestion.key}' field)"
        text = slot.text
        suggestion.paragraph_text = text[:500]
        suggestion.context_before = text[max(0, suggestion.start - 60) : suggestion.start]
        suggestion.context_after = text[suggestion.end : suggestion.end + 60]
        if suggestion.kind == "list":
            suggestion.paragraph_text = suggestion.sample_text[:500]
            suggestion.context_before = ""
            suggestion.context_after = ""
        suggestion.confidence = round(max(0.05, min(0.99, suggestion.confidence)), 2)
    return suggestions


def suggest_cleaning(docx_bytes: bytes) -> SuggestionReport:
    """Analyze an uncleaned DOCX and return cleaning suggestions (read-only)."""
    tpl = DocxTemplate(BytesIO(docx_bytes))
    tpl.init_docx()
    document = tpl.docx
    assert document is not None, "docxtpl failed to initialize the document"
    dmap = walk_document(document)
    existing: list[str] = []
    for slot in dmap.slots:
        for match in re.finditer(r"\{\{\s*([^{}]+?)\s*\}\}", slot.text):
            key = _normalize_token(match.group(1))
            if key and key not in existing:
                existing.append(key)
    analyzer = _Analyzer(dmap)
    analyzer.run()
    suggestions = _finalize(analyzer, set(existing))
    return SuggestionReport(
        suggestions=suggestions,
        existing_keys=existing,
        paragraph_count=len(dmap.slots),
    )
