"""
Shared DOCX walker + formatting-preserving text editing (template pipeline).

Pure XML helpers — NO database access. Used by:
- docx_parser      (placeholder detection, text segments)
- clean_suggester  (cleaning candidates)
- docx_cleaner     (applying replacements)

Every paragraph in the document gets a stable `pid` (paragraph id) assigned
in one canonical traversal order:

    body (document order: paragraphs, tables -> rows -> cells recursively,
    content controls, text boxes anchored in a paragraph right after it),
    then each distinct header/footer part of each section.

Because cleaning ALWAYS starts from the original bytes, a pid computed by the
suggestions endpoint addresses the same paragraph when /clean applies it.

Text boxes are stored twice by Word (mc:AlternateContent -> mc:Choice for
modern Word and mc:Fallback VML for old readers). Only the Choice copy gets
a slot; its Fallback twin is edited in lockstep so both stay identical.

Character offsets match python-docx's `paragraph.text` exactly (runs and
hyperlink runs; w:t, w:tab, w:br, w:cr, w:noBreakHyphen, w:ptab).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_TAG_P = qn("w:p")
_TAG_TBL = qn("w:tbl")
_TAG_TR = qn("w:tr")
_TAG_TC = qn("w:tc")
_TAG_SDT = qn("w:sdt")
_TAG_SDT_CONTENT = qn("w:sdtContent")
_TAG_CUSTOM_XML = qn("w:customXml")
_TAG_T = qn("w:t")
_TAG_R = qn("w:r")
_TAG_RPR = qn("w:rPr")
_TAG_PPR = qn("w:pPr")
_TAG_TXBX = qn("w:txbxContent")
_TAG_MC_ALT = f"{{{MC_NS}}}AlternateContent"
_TAG_MC_FALLBACK = f"{{{MC_NS}}}Fallback"
_TAG_MC_CHOICE = f"{{{MC_NS}}}Choice"

_ATOM_XPATH = "w:br | w:cr | w:noBreakHyphen | w:ptab | w:t | w:tab"

# Existing template syntax must never be edited by cleaning suggestions.
PROTECTED_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)

_HONORIFIC = re.compile(r"^(dr|prof|mr|mrs|ms|shri|smt|sri|er)\.?\s", re.IGNORECASE)
_MANUAL_LIST_PREFIX = re.compile(
    r"^\s*(?:\d{1,2}[.)]|\(\d{1,2}\)|[a-hA-H][.)]|\([a-h]\)|[ivxIVX]{1,4}[.)]|[•\-\*▪●◦‣➢►✓])(?:\s+|$)"
)


@dataclass
class CellInfo:
    """Where a paragraph sits inside a table (merged cells resolved)."""

    table_index: int
    row: int
    col: int  # grid column where the cell starts (gridSpan aware)
    span: int
    vmerge_continue: bool
    first_paragraph: bool
    tc: object = field(repr=False, default=None)


@dataclass
class ParagraphSlot:
    pid: int
    p: object = field(repr=False)
    location: str  # body | table | header | footer | textbox
    text: str
    style_name: str = ""
    is_list_item: bool = False
    has_numbering: bool = False
    manual_list_prefix: str = ""
    is_heading: bool = False
    is_bold: bool = False
    is_centered: bool = False
    cell: CellInfo | None = None
    twins: list = field(default_factory=list, repr=False)
    container_id: int = 0  # id() of the parent container element

    @property
    def stripped(self) -> str:
        return self.text.strip()


@dataclass
class TableCell:
    row: int
    col: int
    span: int
    vmerge_continue: bool
    tc: object = field(repr=False)
    pids: list[int] = field(default_factory=list)
    text: str = ""


@dataclass
class TableInfo:
    index: int
    location: str
    rows: list[list[TableCell]] = field(default_factory=list)


@dataclass
class DocumentMap:
    slots: list[ParagraphSlot] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)

    def slot(self, pid: int) -> ParagraphSlot | None:
        if 0 <= pid < len(self.slots):
            return self.slots[pid]
        return None


# ── text atoms ───────────────────────────────────────────────────────


@dataclass
class _Atom:
    el: object
    run: object
    start: int
    end: int

    @property
    def is_t(self) -> bool:
        return self.el.tag == _TAG_T


def paragraph_text(p) -> str:
    return "".join(str(atom_el) for atom_el, _ in _iter_atom_elements(p))


def _iter_atom_elements(p):
    for run in p.xpath("./w:r | ./w:hyperlink/w:r | ./w:smartTag/w:r | ./w:ins/w:r"):
        for el in run.xpath(_ATOM_XPATH):
            yield el, run


def _atoms(p) -> list[_Atom]:
    atoms: list[_Atom] = []
    position = 0
    for el, run in _iter_atom_elements(p):
        text = str(el)
        if not text:
            continue
        atoms.append(_Atom(el=el, run=run, start=position, end=position + len(text)))
        position += len(text)
    return atoms


def _make_t(text: str):
    t = _new_element("w:t")
    t.text = text
    t.set(XML_SPACE, "preserve")
    return t


def _new_element(tag: str):
    from docx.oxml import OxmlElement

    return OxmlElement(tag)


def _preserve(t) -> None:
    if t.text and (t.text != t.text.strip() or "  " in t.text):
        t.set(XML_SPACE, "preserve")
    elif t.text:
        t.set(XML_SPACE, "preserve")


def _paragraph_mark_rpr(p):
    """A run rPr copied from the paragraph-mark formatting (pPr/rPr), if any."""
    ppr = p.find(_TAG_PPR)
    if ppr is None:
        return None
    mark = ppr.find(_TAG_RPR)
    if mark is None:
        return None
    rpr = copy.deepcopy(mark)
    # Revision-tracking children are only valid on the paragraph mark.
    for child in list(rpr):
        local = child.tag.split("}")[-1]
        if local in {"ins", "del", "moveFrom", "moveTo", "rPrChange"}:
            rpr.remove(child)
    return rpr


def _append_run(p, text: str) -> None:
    run = _new_element("w:r")
    rpr = _paragraph_mark_rpr(p)
    if rpr is not None:
        run.append(rpr)
    run.append(_make_t(text))
    p.append(run)


def replace_span(p, start: int, end: int, new_text: str) -> bool:
    """
    Replace text[start:end] of paragraph `p` with `new_text`, editing only the
    affected text atoms. The new text lands in the run where the span starts,
    so it keeps that run's formatting; other runs (and any drawings/text
    boxes/fields inside them) are untouched. start == end inserts.
    Returns False when the offsets do not fit the paragraph.
    """
    atoms = _atoms(p)
    total = atoms[-1].end if atoms else 0
    if start < 0 or end < start or end > total:
        return False

    if not atoms:
        _append_run(p, new_text)
        return True

    if start == end:
        return _insert_at(atoms, start, new_text)

    placed = False
    for atom in atoms:
        if atom.end <= start or atom.start >= end:
            continue
        local_start = max(start, atom.start) - atom.start
        local_end = min(end, atom.end) - atom.start
        if atom.is_t:
            text = atom.el.text or ""
            if not placed:
                atom.el.text = text[:local_start] + new_text + text[local_end:]
                _preserve(atom.el)
                placed = True
            else:
                remaining = text[:local_start] + text[local_end:]
                if remaining:
                    atom.el.text = remaining
                    _preserve(atom.el)
                else:
                    atom.el.getparent().remove(atom.el)
        else:
            # tab / break / hyphen: a single character, fully covered here.
            if not placed:
                atom.el.addprevious(_make_t(new_text))
                placed = True
            atom.el.getparent().remove(atom.el)
    return placed


def _insert_at(atoms: list[_Atom], position: int, new_text: str) -> bool:
    for atom in atoms:
        if atom.start < position < atom.end and atom.is_t:
            text = atom.el.text or ""
            k = position - atom.start
            atom.el.text = text[:k] + new_text + text[k:]
            _preserve(atom.el)
            return True
    if position == 0:
        atoms[0].el.addprevious(_make_t(new_text))
        return True
    previous = next((a for a in atoms if a.end == position), None)
    if previous is None:
        return False
    if previous.is_t:
        previous.el.text = (previous.el.text or "") + new_text
        _preserve(previous.el)
    else:
        previous.el.addnext(_make_t(new_text))
    return True


def set_paragraph_text(p, text: str) -> None:
    """Replace a paragraph's whole text, keeping the first run's formatting."""
    atoms = _atoms(p)
    if not atoms:
        # Drop empty runs so the paragraph holds exactly one text run.
        _append_run(p, text)
        return
    replace_span(p, 0, atoms[-1].end, text)


def clear_paragraph_runs(p) -> None:
    for child in list(p):
        if child.tag != _TAG_PPR:
            p.remove(child)


def first_run_rpr(p):
    run = p.find(_TAG_R)
    if run is None:
        return None
    rpr = run.find(_TAG_RPR)
    return copy.deepcopy(rpr) if rpr is not None else None


def make_paragraph_like(p, text: str, keep_numbering: bool = True):
    """A new paragraph with p's paragraph properties and one run of `text`."""
    new_p = _new_element("w:p")
    ppr = p.find(_TAG_PPR)
    if ppr is not None:
        new_ppr = copy.deepcopy(ppr)
        if not keep_numbering:
            num = new_ppr.find(qn("w:numPr"))
            if num is not None:
                new_ppr.remove(num)
        new_p.append(new_ppr)
    run = _new_element("w:r")
    rpr = first_run_rpr(p)
    if rpr is not None:
        run.append(rpr)
    run.append(_make_t(text))
    new_p.append(run)
    return new_p


def protected_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in PROTECTED_PATTERN.finditer(text)]


# ── walker ───────────────────────────────────────────────────────────


class _Walker:
    def __init__(self, document: DocumentObject):
        self.document = document
        self.map = DocumentMap()
        self.style_names = self._style_names()
        self.seen_txbx: set[int] = set()
        self.twin_of: dict[int, object] = {}
        self.table_counter = 0
        # lxml proxies are recreated on access and id() values can be reused
        # once a proxy is garbage collected: keep every element we key by id()
        # alive for the whole walk so the ids stay unique.
        self._keep: list = []

    def _remember(self, el) -> int:
        self._keep.append(el)
        return id(el)

    def _style_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        try:
            for style in self.document.styles:
                if style.style_id:
                    names[style.style_id] = style.name or style.style_id
        except Exception:  # missing/odd styles part: fall back to ids
            pass
        return names

    def run(self) -> DocumentMap:
        body = self.document.element.body
        self._walk_container(body, "body", cell=None)
        seen_parts: set[int] = set()
        for section in self.document.sections:
            parts = (
                (section.header, "header"),
                (section.first_page_header, "header"),
                (section.even_page_header, "header"),
                (section.footer, "footer"),
                (section.first_page_footer, "footer"),
                (section.even_page_footer, "footer"),
            )
            for hf, location in parts:
                try:
                    if hf is None or hf.is_linked_to_previous:
                        continue
                    part = hf.part
                except Exception:
                    continue
                if id(part) in seen_parts or part is self.document.part:
                    continue
                seen_parts.add(id(part))
                self._walk_container(part.element, location, cell=None)
        self._mark_headings()
        return self.map

    def _walk_container(self, container, location: str, cell: CellInfo | None) -> None:
        first_paragraph = True
        for child in container.iterchildren():
            tag = child.tag
            if tag == _TAG_P:
                cell_info = None
                if cell is not None:
                    cell_info = CellInfo(
                        table_index=cell.table_index,
                        row=cell.row,
                        col=cell.col,
                        span=cell.span,
                        vmerge_continue=cell.vmerge_continue,
                        first_paragraph=first_paragraph,
                        tc=cell.tc,
                    )
                first_paragraph = False
                self._add_paragraph(child, location, cell_info, container)
            elif tag == _TAG_TBL:
                self._walk_table(child, location)
            elif tag == _TAG_SDT:
                content = child.find(_TAG_SDT_CONTENT)
                if content is not None:
                    self._walk_container(content, location, cell)
            elif tag == _TAG_CUSTOM_XML:
                self._walk_container(child, location, cell)

    def _walk_table(self, tbl, location: str) -> None:
        table = TableInfo(index=self.table_counter, location=location)
        self.table_counter += 1
        self.map.tables.append(table)
        cell_location = "table" if location == "body" else location
        for row_index, tr in enumerate(tbl.iterchildren(_TAG_TR)):
            row_cells: list[TableCell] = []
            col = 0
            for tc in tr.iterchildren(_TAG_TC):
                tc_pr = tc.find(qn("w:tcPr"))
                span = 1
                vmerge_continue = False
                if tc_pr is not None:
                    grid_span = tc_pr.find(qn("w:gridSpan"))
                    if grid_span is not None:
                        try:
                            span = int(grid_span.get(qn("w:val")) or 1)
                        except ValueError:
                            span = 1
                    v_merge = tc_pr.find(qn("w:vMerge"))
                    if v_merge is not None and v_merge.get(qn("w:val")) != "restart":
                        vmerge_continue = True
                cell = TableCell(
                    row=row_index,
                    col=col,
                    span=span,
                    vmerge_continue=vmerge_continue,
                    tc=tc,
                )
                before = len(self.map.slots)
                self._walk_container(
                    tc,
                    cell_location,
                    CellInfo(
                        table_index=table.index,
                        row=row_index,
                        col=col,
                        span=span,
                        vmerge_continue=vmerge_continue,
                        first_paragraph=True,
                        tc=tc,
                    ),
                )
                cell.pids = [
                    slot.pid
                    for slot in self.map.slots[before:]
                    if slot.cell is not None and slot.cell.tc is tc
                ]
                cell.text = "\n".join(
                    self.map.slots[pid].text for pid in cell.pids
                ).strip()
                row_cells.append(cell)
                col += span
            table.rows.append(row_cells)

    def _add_paragraph(self, p, location: str, cell: CellInfo | None, container) -> None:
        text = paragraph_text(p)
        style_name = self._paragraph_style(p)
        ppr = p.find(_TAG_PPR)
        has_numbering = ppr is not None and ppr.find(qn("w:numPr")) is not None
        if not has_numbering and style_name.lower().startswith("list"):
            has_numbering = style_name.lower().startswith(("list number", "list bullet"))
        manual = _MANUAL_LIST_PREFIX.match(text)
        manual_prefix = manual.group(0) if manual else ""
        bold = _all_text_bold(p)
        jc = ppr.find(qn("w:jc")) if ppr is not None else None
        centered = jc is not None and jc.get(qn("w:val")) in ("center",)
        slot = ParagraphSlot(
            pid=len(self.map.slots),
            p=p,
            location=location,
            text=text,
            style_name=style_name,
            is_list_item=has_numbering or bool(manual_prefix),
            has_numbering=has_numbering,
            manual_list_prefix=manual_prefix,
            is_bold=bold,
            is_centered=centered,
            cell=cell,
            twins=[self.twin_of[id(p)]] if id(p) in self.twin_of else [],
            container_id=self._remember(container),
        )
        self.map.slots.append(slot)
        self._walk_textboxes(p)

    def _walk_textboxes(self, p) -> None:
        for txbx in p.iter(_TAG_TXBX):
            if id(txbx) in self.seen_txbx:
                continue
            self.seen_txbx.add(self._remember(txbx))
            if _has_ancestor(txbx, _TAG_MC_FALLBACK, stop=p):
                continue
            # Pair the Choice text box with its VML Fallback twin.
            alternate = _ancestor(txbx, _TAG_MC_ALT, stop=p)
            if alternate is not None:
                choice_boxes = [
                    box
                    for box in alternate.iter(_TAG_TXBX)
                    if not _has_ancestor(box, _TAG_MC_FALLBACK, stop=alternate)
                ]
                fallback_boxes = [
                    box
                    for box in alternate.iter(_TAG_TXBX)
                    if _has_ancestor(box, _TAG_MC_FALLBACK, stop=alternate)
                ]
                if txbx in choice_boxes and len(choice_boxes) == len(fallback_boxes):
                    twin_box = fallback_boxes[choice_boxes.index(txbx)]
                    self.seen_txbx.add(self._remember(twin_box))
                    choice_ps = list(txbx.iter(_TAG_P))
                    fallback_ps = list(twin_box.iter(_TAG_P))
                    if len(choice_ps) == len(fallback_ps):
                        for choice_p, fallback_p in zip(choice_ps, fallback_ps):
                            self.twin_of[self._remember(choice_p)] = fallback_p
            self._walk_container(txbx, "textbox", cell=None)

    def _paragraph_style(self, p) -> str:
        ppr = p.find(_TAG_PPR)
        if ppr is None:
            return "Normal"
        style = ppr.find(qn("w:pStyle"))
        if style is None:
            return "Normal"
        style_id = style.get(qn("w:val")) or ""
        return self.style_names.get(style_id, style_id)

    def _mark_headings(self) -> None:
        slots = self.map.slots
        for index, slot in enumerate(slots):
            slot.is_heading = _looks_like_heading(slot, _next_non_empty(slots, index))


def _ancestor(el, tag, stop=None):
    parent = el.getparent()
    while parent is not None and parent is not stop:
        if parent.tag == tag:
            return parent
        parent = parent.getparent()
    return None


def _has_ancestor(el, tag, stop=None) -> bool:
    return _ancestor(el, tag, stop) is not None


def _all_text_bold(p) -> bool:
    saw_text = False
    for el, run in _iter_atom_elements(p):
        if not str(el).strip():
            continue
        saw_text = True
        rpr = run.find(_TAG_RPR)
        bold = rpr.find(qn("w:b")) if rpr is not None else None
        if bold is None or bold.get(qn("w:val")) in ("0", "false", "off"):
            return False
    return saw_text


def _next_non_empty(slots: list[ParagraphSlot], index: int) -> ParagraphSlot | None:
    current = slots[index]
    for slot in slots[index + 1 : index + 6]:
        if slot.location != current.location and current.location != "table":
            return None
        if slot.stripped:
            return slot
    return None


def _looks_like_heading(slot: ParagraphSlot, following: ParagraphSlot | None) -> bool:
    text = slot.stripped
    if not text or slot.is_list_item or slot.cell is not None:
        return False
    style = slot.style_name.lower()
    if style.startswith("heading") or style in ("title", "subtitle"):
        return True
    if len(text) > 60 or len(text.split()) > 7:
        return False
    if text[-1] in ".,;:" or "{{" in text or _HONORIFIC.match(text):
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    letters = [ch for ch in text if ch.isalpha()]
    upper = len(letters) >= 3 and all(ch.isupper() for ch in letters)
    if not (slot.is_bold or upper):
        return False
    if slot.is_centered:
        return True
    if following is None:
        return False
    return (not following.is_bold) or following.is_list_item


def walk_document(document: DocumentObject) -> DocumentMap:
    """Build the canonical paragraph map of a python-docx Document."""
    return _Walker(document).run()


def iter_all_paragraph_elements(dmap: DocumentMap):
    """Every paragraph element including Fallback twins (for global edits)."""
    for slot in dmap.slots:
        yield slot, slot.p
        for twin in slot.twins:
            yield slot, twin
