/**
 * Rich text for long-text (textarea) fields: the editor's Tiptap JSON, the
 * whitelist the backend accepts, and its plain-text projection.
 *
 * Mirrors backend/app/services/rich_text.py exactly:
 * - nodes: doc, paragraph, text, hardBreak, bulletList, orderedList, listItem
 *   (lists nested at most 3 levels)
 * - marks: bold, italic, underline, strike, highlight, link (http, https,
 *   mailto); link keeps only href, orderedList only start (1..999)
 * - docToPlain: blocks joined by "\n"; hardBreak "\n"; bullet item "• ",
 *   nested bullets "◦ ", ordered "1. " (respecting start); 4 spaces per
 *   nesting level; a list item's later paragraphs one level deeper;
 *   trailing whitespace removed. The generated DOCX shows exactly this text.
 *
 * normalizeDoc is lenient where the backend is strict: whatever the editor
 * holds (pasted headings, tables, deep lists, unsafe links...) becomes a doc
 * the backend accepts, keeping the text. So saving never fails with
 * "Unsupported formatting".
 *
 * Kept free of React and `@/` imports so it can be unit tested with
 * `node --test` (frontend/tests/rich-model.test.ts).
 */

export interface RichMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface RichNode {
  type: string;
  text?: string;
  marks?: RichMark[];
  attrs?: Record<string, unknown>;
  content?: RichNode[];
}

export interface RichDoc extends RichNode {
  type: "doc";
  content: RichNode[];
}

/** The react-hook-form value of a textarea field. */
export interface RichValue {
  format: "rich";
  doc: RichDoc;
}

export const ALLOWED_NODES = ["doc", "paragraph", "text", "hardBreak", "bulletList", "orderedList", "listItem"] as const;
export const ALLOWED_MARKS = ["bold", "italic", "underline", "strike", "link", "highlight"] as const;
export const LINK_PROTOCOLS = ["http://", "https://", "mailto:"] as const;
export const MAX_LIST_DEPTH = 3;
export const MAX_JSON_BYTES = 50_000;
export const MAX_TEXT_CHARS = 20_000;
const MAX_LINK_LENGTH = 2048;
const MAX_ORDERED_START = 999;

export const BULLET = "• ";
export const NESTED_BULLET = "◦ ";
export const INDENT = "    ";

const MARK_ORDER = ["bold", "italic", "underline", "strike", "highlight", "link"];
const LIST_TYPES = new Set(["bulletList", "orderedList"]);
// Same rule as the backend: keep \t and \n, drop other C0 controls and DEL.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u0008\u000b-\u001f\u007f]/g;

// ── Values ────────────────────────────────────────────────────────

export function emptyDoc(): RichDoc {
  return { type: "doc", content: [{ type: "paragraph" }] };
}

export function richValue(doc: RichDoc): RichValue {
  return { format: "rich", doc };
}

export function isRichValue(value: unknown): value is RichValue {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as RichValue).format === "rich" &&
    typeof (value as RichValue).doc === "object" &&
    (value as RichValue).doc !== null
  );
}

/** Plain text (one paragraph per line) as a doc: how old plain values open in the editor. */
export function plainToDoc(text: string | null | undefined): RichDoc {
  const clean = (text ?? "").replace(/\r\n?/g, "\n").replace(CONTROL_CHARS, "");
  const content: RichNode[] = clean.split("\n").map((line) =>
    line ? { type: "paragraph", content: [{ type: "text", text: line }] } : { type: "paragraph" },
  );
  return { type: "doc", content };
}

// ── Links ─────────────────────────────────────────────────────────

/** The href the backend accepts (trimmed), or null. */
export function allowedHref(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const href = raw.trim();
  if (!href || href.length > MAX_LINK_LENGTH) return null;
  if (/[\s\u0000-\u001f]/.test(href)) return null;
  const lower = href.toLowerCase();
  return LINK_PROTOCOLS.some((protocol) => lower.startsWith(protocol)) ? href : null;
}

// ── Strict check (backend parity) ─────────────────────────────────

/**
 * True when the backend validator accepts `doc` as is (same structure
 * rules). Unknown attributes are allowed: the backend drops them.
 */
export function isAllowedDoc(doc: unknown): boolean {
  try {
    if (!isNode(doc) || doc.type !== "doc") return false;
    for (const block of children(doc)) checkBlock(block);
    return docToPlain(doc as RichDoc).length <= MAX_TEXT_CHARS && jsonBytes(doc) <= MAX_JSON_BYTES;
  } catch {
    return false;
  }
}

function isNode(value: unknown): value is RichNode {
  return typeof value === "object" && value !== null && !Array.isArray(value) && typeof (value as RichNode).type === "string";
}

function children(node: RichNode): RichNode[] {
  if (node.content === undefined || node.content === null) return [];
  if (!Array.isArray(node.content)) throw new Error("structure");
  return node.content;
}

function checkMarks(marks: unknown): void {
  if (marks === undefined || marks === null) return;
  if (!Array.isArray(marks)) throw new Error("structure");
  for (const mark of marks) {
    if (!isNode(mark) || !(ALLOWED_MARKS as readonly string[]).includes(mark.type)) throw new Error("mark");
    if (mark.type === "link" && allowedHref(mark.attrs?.href) === null) throw new Error("link");
  }
}

function checkInline(node: unknown): void {
  if (!isNode(node)) throw new Error("structure");
  if (node.type === "hardBreak") return;
  if (node.type !== "text" || typeof node.text !== "string" || node.text === "") throw new Error("inline");
  checkMarks(node.marks);
}

function checkList(node: RichNode, depth: number): void {
  if (depth > MAX_LIST_DEPTH) throw new Error("depth");
  const items = children(node);
  if (items.length === 0) throw new Error("empty list");
  if (node.type === "orderedList") {
    const start = node.attrs?.start ?? 1;
    if (start !== null && (typeof start !== "number" || !Number.isInteger(start) || start < 1 || start > MAX_ORDERED_START)) {
      throw new Error("start");
    }
  }
  for (const item of items) {
    if (!isNode(item) || item.type !== "listItem") throw new Error("structure");
    const parts = children(item);
    if (parts.length === 0) throw new Error("structure");
    parts.forEach((part, index) => {
      if (!isNode(part)) throw new Error("structure");
      if (part.type === "paragraph") children(part).forEach(checkInline);
      else if (LIST_TYPES.has(part.type) && index > 0) checkList(part, depth + 1);
      else throw new Error("structure");
    });
  }
}

function checkBlock(node: unknown): void {
  if (!isNode(node)) throw new Error("structure");
  if (node.type === "paragraph") children(node).forEach(checkInline);
  else if (LIST_TYPES.has(node.type)) checkList(node, 1);
  else throw new Error("node");
}

function jsonBytes(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value)).length;
}

// ── Lenient normalization (what the editor emits) ────────────────

function normalizeMarks(marks: unknown): RichMark[] {
  if (!Array.isArray(marks)) return [];
  const found = new Map<string, RichMark>();
  for (const mark of marks) {
    if (!isNode(mark) || !(ALLOWED_MARKS as readonly string[]).includes(mark.type)) continue;
    if (mark.type === "link") {
      const href = allowedHref(mark.attrs?.href);
      if (href) found.set("link", { type: "link", attrs: { href } });
    } else {
      found.set(mark.type, { type: mark.type });
    }
  }
  return MARK_ORDER.filter((name) => found.has(name)).map((name) => found.get(name)!);
}

/** Inline content of any node, flattened: text nodes and hard breaks. */
function inlineOf(node: RichNode): RichNode[] {
  const out: RichNode[] = [];
  const visit = (current: unknown) => {
    if (!isNode(current)) return;
    if (current.type === "text") {
      const text = typeof current.text === "string" ? current.text.replace(/\r\n?/g, "\n").replace(CONTROL_CHARS, "") : "";
      if (!text) return;
      const marks = normalizeMarks(current.marks);
      out.push(marks.length ? { type: "text", text, marks } : { type: "text", text });
    } else if (current.type === "hardBreak") {
      out.push({ type: "hardBreak" });
    } else if (Array.isArray(current.content)) {
      current.content.forEach(visit);
    }
  };
  (Array.isArray(node.content) ? node.content : []).forEach(visit);
  return out;
}

function paragraph(content: RichNode[]): RichNode {
  return content.length ? { type: "paragraph", content } : { type: "paragraph" };
}

/** Any block (heading, quote, code, table, task list...) as allowed blocks with its text. */
function normalizeBlock(node: unknown, depth: number): RichNode[] {
  if (!isNode(node)) return [];
  if (node.type === "paragraph" || node.type === "heading" || node.type === "codeBlock") {
    return [paragraph(inlineOf(node))];
  }
  if (node.type === "text" || node.type === "hardBreak") {
    return [paragraph(inlineOf({ type: "paragraph", content: [node] }))];
  }
  if (LIST_TYPES.has(node.type) || node.type === "taskList") {
    const list = normalizeList(node, depth + 1);
    return list ? [list] : [];
  }
  // blockquote, table, rows, cells, unknown containers: keep their blocks.
  const out: RichNode[] = [];
  for (const child of Array.isArray(node.content) ? node.content : []) out.push(...normalizeBlock(child, depth));
  return out;
}

function normalizeList(node: RichNode, depth: number): RichNode | null {
  const type = node.type === "orderedList" ? "orderedList" : "bulletList";
  const items: RichNode[] = [];
  for (const item of Array.isArray(node.content) ? node.content : []) {
    if (!isNode(item)) continue;
    const parts: RichNode[] = [];
    for (const child of Array.isArray(item.content) ? item.content : []) {
      if (!isNode(child)) continue;
      if (LIST_TYPES.has(child.type) || child.type === "taskList") {
        if (depth < MAX_LIST_DEPTH) {
          const nested = normalizeList(child, depth + 1);
          if (nested) parts.push(nested);
        } else {
          // Too deep: the nested items become paragraphs of this item.
          parts.push(...flattenListToParagraphs(child));
        }
      } else {
        parts.push(...normalizeBlock(child, depth));
      }
    }
    if (parts.length === 0 || parts[0].type !== "paragraph") parts.unshift({ type: "paragraph" });
    items.push({ type: "listItem", content: parts });
  }
  if (items.length === 0) return null;
  const list: RichNode = { type, content: items };
  if (type === "orderedList") {
    const start = node.attrs?.start;
    if (typeof start === "number" && Number.isInteger(start) && start > 1 && start <= MAX_ORDERED_START) {
      list.attrs = { start };
    }
  }
  return list;
}

function flattenListToParagraphs(node: RichNode): RichNode[] {
  const out: RichNode[] = [];
  for (const item of Array.isArray(node.content) ? node.content : []) {
    if (!isNode(item)) continue;
    for (const child of Array.isArray(item.content) ? item.content : []) {
      if (!isNode(child)) continue;
      if (LIST_TYPES.has(child.type) || child.type === "taskList") out.push(...flattenListToParagraphs(child));
      else out.push(...normalizeBlock(child, MAX_LIST_DEPTH));
    }
  }
  return out;
}

/**
 * Any editor JSON as a doc the backend accepts, in the backend's normalized
 * shape (same keys, mark order, attrs): unsupported formatting is dropped,
 * its text kept. An empty result is one empty paragraph.
 */
export function normalizeDoc(doc: unknown): RichDoc {
  if (!isNode(doc)) return emptyDoc();
  const content: RichNode[] = [];
  for (const block of Array.isArray(doc.content) ? doc.content : []) content.push(...normalizeBlock(block, 0));
  return { type: "doc", content: content.length ? content : [{ type: "paragraph" }] };
}

/** Same content after normalization. */
export function sameDoc(a: unknown, b: unknown): boolean {
  return JSON.stringify(normalizeDoc(a)) === JSON.stringify(normalizeDoc(b));
}

// ── Plain text and blocks ─────────────────────────────────────────

export interface ParagraphEntry {
  paragraph: RichNode;
  kind: "p" | "bullet" | "ordered";
  depth: number;
  prefix: string;
}

/** Every paragraph in document order (backend iter_paragraphs). */
export function iterParagraphs(doc: RichDoc): ParagraphEntry[] {
  const out: ParagraphEntry[] = [];
  const walkList = (node: RichNode, depth: number) => {
    const ordered = node.type === "orderedList";
    const start = typeof node.attrs?.start === "number" ? (node.attrs.start as number) : 1;
    const indent = INDENT.repeat(depth - 1);
    (node.content ?? []).forEach((item, position) => {
      const kind = ordered ? "ordered" : "bullet";
      const marker = ordered ? `${start + position}. ` : depth === 1 ? BULLET : NESTED_BULLET;
      let first = true;
      for (const child of item.content ?? []) {
        if (child.type === "paragraph") {
          out.push(first ? { paragraph: child, kind, depth, prefix: indent + marker } : { paragraph: child, kind: "p", depth, prefix: INDENT.repeat(depth) });
          first = false;
        } else if (LIST_TYPES.has(child.type)) {
          walkList(child, depth + 1);
        }
      }
    });
  };
  for (const block of doc.content ?? []) {
    if (block.type === "paragraph") out.push({ paragraph: block, kind: "p", depth: 0, prefix: "" });
    else if (LIST_TYPES.has(block.type)) walkList(block, 1);
  }
  return out;
}

export function paragraphText(paragraph: RichNode): string {
  return (paragraph.content ?? []).map((node) => (node.type === "hardBreak" ? "\n" : node.text ?? "")).join("");
}

/** Python str.rstrip(): trailing whitespace. */
function rstrip(text: string): string {
  return text.replace(/\s+$/u, "");
}

/** The plain-text projection; equals the backend's to_plain_text. */
export function docToPlain(doc: RichDoc): string {
  return rstrip(iterParagraphs(doc).map(({ paragraph, prefix }) => prefix + paragraphText(paragraph)).join("\n"));
}

export function countChars(doc: RichDoc): number {
  return docToPlain(doc).length;
}

/** One text per paragraph, in order (backend to_blocks texts). */
export function docToBlocks(doc: RichDoc): string[] {
  return iterParagraphs(doc).map(({ paragraph }) => paragraphText(paragraph));
}

function textContent(text: string): RichNode[] {
  const content: RichNode[] = [];
  text.split("\n").forEach((line, index) => {
    if (index) content.push({ type: "hardBreak" });
    if (line) content.push({ type: "text", text: line });
  });
  return content;
}

/**
 * The doc with each paragraph's text replaced by texts[i] (docToBlocks
 * order). Structure is kept; a rewritten paragraph loses its marks, an
 * unchanged one keeps them. Throws when the counts differ.
 */
export function blocksToDoc(doc: RichDoc, texts: string[]): RichDoc {
  const copy = JSON.parse(JSON.stringify(doc)) as RichDoc;
  const entries = iterParagraphs(copy);
  if (entries.length !== texts.length) throw new Error("The rewritten text does not match the paragraphs");
  entries.forEach(({ paragraph }, index) => {
    const text = texts[index];
    if (typeof text !== "string") throw new Error("The rewritten text does not match the paragraphs");
    if (text === paragraphText(paragraph)) return;
    const content = textContent(text.replace(/\r\n?/g, "\n"));
    if (content.length) paragraph.content = content;
    else delete paragraph.content;
  });
  return copy;
}

/** The non-blank paragraphs (what AI rewrites) and their positions in docToBlocks. */
export function aiBlocks(doc: RichDoc): { indexes: number[]; items: string[] } {
  const indexes: number[] = [];
  const items: string[] = [];
  docToBlocks(doc).forEach((text, index) => {
    if (text.trim()) {
      indexes.push(index);
      items.push(text.trim());
    }
  });
  return { indexes, items };
}

/** Put AI results back in place of the non-blank paragraphs (others unchanged). */
export function applyAiBlocks(doc: RichDoc, indexes: number[], improved: string[]): RichDoc {
  if (indexes.length !== improved.length) throw new Error("The AI changed the number of paragraphs");
  const texts = docToBlocks(doc);
  indexes.forEach((blockIndex, i) => {
    texts[blockIndex] = improved[i];
  });
  return blocksToDoc(doc, texts);
}

/** JSON size and text limits the backend enforces; a user-facing message or null. */
export function richLimitError(doc: RichDoc): string | null {
  if (countChars(doc) > MAX_TEXT_CHARS) return `The text must be at most ${MAX_TEXT_CHARS.toLocaleString("en-US")} characters`;
  if (jsonBytes(doc) > MAX_JSON_BYTES) return "This text has too much formatting to save. Remove some formatting or split it.";
  return null;
}
