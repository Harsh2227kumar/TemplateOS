// Run with `npm test`. Rich text model (V1.7 P2): whitelist parity with the
// backend (backend/app/services/rich_text.py), plain projection, blocks.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  aiBlocks,
  applyAiBlocks,
  blocksToDoc,
  countChars,
  docToBlocks,
  docToPlain,
  isAllowedDoc,
  isRichValue,
  normalizeDoc,
  plainToDoc,
  richLimitError,
  richValue,
  sameDoc,
  type RichDoc,
  type RichNode,
} from "../src/features/rich-text/rich-model.ts";

type Mark = { type: string; attrs?: Record<string, unknown> };
const text = (value: string, ...marks: Mark[]): RichNode =>
  marks.length ? { type: "text", text: value, marks } : { type: "text", text: value };
const para = (...content: RichNode[]): RichNode => (content.length ? { type: "paragraph", content } : { type: "paragraph" });
const item = (...content: RichNode[]): RichNode => ({ type: "listItem", content });
const bullets = (...items: RichNode[]): RichNode => ({ type: "bulletList", content: items });
const numbers = (start: number | null, ...items: RichNode[]): RichNode => ({
  type: "orderedList",
  ...(start === null ? {} : { attrs: { start, type: null } }),
  content: items,
});
const doc = (...content: RichNode[]): RichDoc => ({ type: "doc", content });
const BOLD = { type: "bold" };
const link = (href: string) => ({ type: "link", attrs: { href, target: "_blank", rel: "noopener", class: null } });

// Shared test vector: backend/tests/test_rich_text.py asserts the same plain text.
const SHARED_DOC = doc(
  para(text("Intro with "), text("bold", BOLD), text(" and a "), text("link", link("https://example.com")), { type: "hardBreak" }, text("second line")),
  bullets(item(para(text("Apples")), bullets(item(para(text("Green"))))), item(para(text("Pears")))),
  numbers(
    3,
    item(para(text("Third", { type: "italic" }, { type: "highlight", attrs: { color: "#ff0" } })), para(text("more"))),
    item(para(text("Fourth & <last>")), numbers(null, item(para(text("Sub"))))),
  ),
  para(),
);
const SHARED_PLAIN =
  "Intro with bold and a link\nsecond line\n• Apples\n    ◦ Green\n• Pears\n3. Third\n    more\n4. Fourth & <last>\n    1. Sub";

test("shared vector: plain projection equals the backend's", () => {
  assert.equal(docToPlain(SHARED_DOC), SHARED_PLAIN);
  assert.equal(docToPlain(normalizeDoc(SHARED_DOC)), SHARED_PLAIN);
  assert.equal(countChars(SHARED_DOC), SHARED_PLAIN.length);
});

test("normalizeDoc produces the backend's normalized shape", () => {
  const normalized = normalizeDoc(SHARED_DOC);
  const intro = normalized.content[0].content!;
  assert.deepEqual(intro[3].marks, [{ type: "link", attrs: { href: "https://example.com" } }]);
  const third = normalized.content[2].content![0].content![0].content![0];
  assert.deepEqual(third.marks, [{ type: "italic" }, { type: "highlight" }]);
  assert.deepEqual(normalized.content[2].attrs, { start: 3 });
  assert.equal(normalized.content[2].content![1].content![1].attrs, undefined); // start 1 dropped
  assert.deepEqual(normalized.content[3], { type: "paragraph" });
  assert.deepEqual(normalizeDoc(normalized), normalized);
  assert.equal(isAllowedDoc(normalized), true);
});

test("isAllowedDoc mirrors the backend whitelist", () => {
  assert.equal(isAllowedDoc(SHARED_DOC), true); // extra attrs are dropped by the server, not rejected
  assert.equal(isAllowedDoc(doc()), true);
  assert.equal(isAllowedDoc(doc({ type: "heading", attrs: { level: 1 }, content: [text("T")] })), false);
  assert.equal(isAllowedDoc(doc({ type: "image", attrs: { src: "x.png" } })), false);
  assert.equal(isAllowedDoc(doc({ type: "codeBlock", content: [text("x")] })), false);
  assert.equal(isAllowedDoc(doc(para(text("x", { type: "code" })))), false);
  assert.equal(isAllowedDoc(doc(para(text("x", link("javascript:alert(1)"))))), false);
  assert.equal(isAllowedDoc(doc(para(text("x", link("mailto:a@b.c"))))), true);
  assert.equal(isAllowedDoc(doc(para(text("")))), false);
  assert.equal(isAllowedDoc(doc(text("loose"))), false);
  assert.equal(isAllowedDoc(doc(bullets())), false);
  assert.equal(isAllowedDoc(doc(bullets(item(bullets(item(para(text("x")))))))), false);
  assert.equal(isAllowedDoc(doc(numbers(0, item(para(text("x")))))), false);
  const deep = bullets(item(para(text("1")), bullets(item(para(text("2")), bullets(item(para(text("3")), bullets(item(para(text("4"))))))))));
  assert.equal(isAllowedDoc(doc(deep)), false);
  assert.equal(isAllowedDoc({ type: "paragraph" }), false);
  assert.equal(isAllowedDoc(null), false);
});

test("normalizeDoc keeps the text of anything pasted (never a 422)", () => {
  const pasted = {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [text("Title", BOLD)] },
      { type: "blockquote", content: [para(text("Quoted"))] },
      { type: "codeBlock", content: [text("code()")] },
      { type: "image", attrs: { src: "x.png" } },
      { type: "table", content: [{ type: "tableRow", content: [{ type: "tableCell", content: [para(text("Cell"))] }] }] },
      { type: "taskList", content: [{ type: "taskItem", attrs: { checked: true }, content: [para(text("Task"))] }] },
      para(text("bad link", link("javascript:alert(1)")), text(" ok", { type: "superscript" })),
      text("loose text"),
      bullets(item(bullets(item(para(text("starts with a list")))))),
      bullets(item(para(text("1")), bullets(item(para(text("2")), bullets(item(para(text("3")), bullets(item(para(text("4 deep")))))))))),
    ],
  };
  const normalized = normalizeDoc(pasted);
  assert.equal(isAllowedDoc(normalized), true);
  assert.equal(
    docToPlain(normalized),
    [
      "Title",
      "Quoted",
      "code()",
      "Cell",
      "• Task",
      "bad link ok",
      "loose text",
      "• ",
      "    ◦ starts with a list",
      "• 1",
      "    ◦ 2",
      "        ◦ 3",
      "            4 deep",
    ].join("\n"),
  );
  // Formatting of kept text survives; unsupported marks and links do not.
  assert.deepEqual(normalized.content[0], { type: "paragraph", content: [text("Title", BOLD)] });
  assert.deepEqual(normalized.content[5], { type: "paragraph", content: [text("bad link"), text(" ok")] });
  assert.deepEqual(normalizeDoc(null), { type: "doc", content: [{ type: "paragraph" }] });
});

test("control characters are removed like on the server", () => {
  const normalized = normalizeDoc(doc(para(text("a\u0000b\u0007"), text("\u000b", BOLD), text("c\r\nd\te"))));
  assert.deepEqual(normalized, doc(para(text("ab"), text("c\nd\te"))));
  assert.equal(docToPlain(normalized), "abc\nd\te");
});

test("plain text and docs", () => {
  assert.equal(docToPlain(plainToDoc("line 1\n\nline 3\r\nline 4")), "line 1\n\nline 3\nline 4");
  assert.equal(docToPlain(plainToDoc("")), "");
  assert.equal(docToPlain(doc(para(text("trailing   ")), para())), "trailing");
  assert.equal(docToPlain(doc(numbers(9, item(para(text("a"))), item(para(text("b")))))), "9. a\n10. b");
  assert.equal(docToPlain(doc(para(text("emoji 🎉 & < > ✓")))), "emoji 🎉 & < > ✓");
  assert.equal(isRichValue(richValue(plainToDoc("x"))), true);
  assert.equal(isRichValue("x"), false);
  assert.equal(sameDoc(SHARED_DOC, normalizeDoc(SHARED_DOC)), true);
  assert.equal(sameDoc(plainToDoc("a"), plainToDoc("b")), false);
});

test("blocks round trip and keep structure", () => {
  const normalized = normalizeDoc(SHARED_DOC);
  const blocks = docToBlocks(normalized);
  assert.deepEqual(blocks, [
    "Intro with bold and a link\nsecond line",
    "Apples",
    "Green",
    "Pears",
    "Third",
    "more",
    "Fourth & <last>",
    "Sub",
    "",
  ]);
  assert.deepEqual(blocksToDoc(normalized, blocks), normalized);
  const rewritten = blocksToDoc(normalized, ["Rewritten intro\nline two", "Red apples", ...blocks.slice(2)]);
  assert.deepEqual(rewritten.content[0], { type: "paragraph", content: [text("Rewritten intro"), { type: "hardBreak" }, text("line two")] });
  assert.equal(docToPlain(rewritten).startsWith("Rewritten intro\nline two\n• Red apples\n    ◦ Green"), true);
  // Untouched paragraphs keep their marks; the input is not mutated.
  assert.deepEqual(rewritten.content[2], normalized.content[2]);
  assert.equal(docToPlain(normalized), SHARED_PLAIN);
  assert.throws(() => blocksToDoc(normalized, ["only one"]));
});

test("AI blocks skip blank paragraphs and go back in place", () => {
  const source = normalizeDoc(doc(para(text("first")), para(), bullets(item(para(text(" second "))))));
  const { indexes, items } = aiBlocks(source);
  assert.deepEqual(indexes, [0, 2]);
  assert.deepEqual(items, ["first", "second"]);
  const result = applyAiBlocks(source, indexes, ["First.", "Second."]);
  assert.equal(docToPlain(result), "First.\n\n• Second.");
  assert.throws(() => applyAiBlocks(source, indexes, ["one"]));
});

test("size limits", () => {
  assert.equal(richLimitError(plainToDoc("x".repeat(20_000))), null);
  assert.match(richLimitError(plainToDoc("x".repeat(20_001))) ?? "", /at most 20,000 characters/);
  const heavy = doc(...Array.from({ length: 400 }, () => para(text("formatted text", BOLD, { type: "italic" }, { type: "underline" }))));
  assert.match(richLimitError(heavy) ?? "", /too much formatting/);
});
