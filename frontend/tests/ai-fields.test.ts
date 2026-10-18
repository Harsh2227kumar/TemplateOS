// Run with `npm test`. AI on list fields and the "Rewrite all with AI" planner.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  AI_FIELD_TYPES,
  aiFieldKind,
  aiTextOf,
  aiTextToList,
  listToAiText,
  normalizeAiResultFor,
  planRewriteAll,
  sameFieldValue,
  styleAppliesTo,
  type AiFieldKind,
} from "../src/components/fields/ai-style-state.ts";
import { docToPlain, plainToDoc, richValue } from "../src/features/rich-text/rich-model.ts";

// Rich (textarea) fields measure the plain text of the doc, as the hook does.
const measureFor = (kind: AiFieldKind) =>
  kind === "rich"
    ? (text: string) => {
        const plain = text ? docToPlain(JSON.parse(text)) : "";
        return { empty: !plain.trim(), length: plain.length };
      }
    : (text: string) => ({ empty: !text.trim(), length: text.length });
const rich = (text: string) => richValue(plainToDoc(text));
const richText = (text: string) => JSON.stringify(plainToDoc(text));

test("AI applies to text, paragraph and list fields only", () => {
  assert.equal(aiFieldKind("text"), "text");
  assert.equal(aiFieldKind("textarea"), "rich");
  assert.equal(aiFieldKind("list"), "list");
  for (const type of ["date", "time", "number", "email", "signature"]) {
    assert.equal(aiFieldKind(type), null, type);
    assert.equal(AI_FIELD_TYPES.includes(type), false, type);
  }
});

test("list values round-trip through switcher text", () => {
  assert.equal(listToAiText(["Venue booking", "", "Budget"]), "Venue booking\n\nBudget");
  assert.deepEqual(aiTextToList(" Venue booking \n\n Budget "), ["Venue booking", "Budget"]);
  assert.equal(listToAiText("not a list"), "");
  assert.equal(aiTextOf("list", ["a", "b"]), "a\nb");
  assert.equal(aiTextOf("text", null), "");
});

test("AI results are cleaned per field kind", () => {
  assert.equal(normalizeAiResultFor("list", " One \n\n Two "), "One\nTwo");
  assert.equal(normalizeAiResultFor("text", "One\nTwo"), "One Two");
  assert.equal(normalizeAiResultFor("multiline", "One\r\nTwo\n"), "One\nTwo");
});

test("Expand is not offered on one-line inputs", () => {
  assert.equal(styleAppliesTo("expand", "text"), false);
  assert.equal(styleAppliesTo("expand", "multiline"), true);
  assert.equal(styleAppliesTo("expand", "list"), true);
  assert.equal(styleAppliesTo("formal", "text"), true);
});

const fields = [
  { field_name: "title", field_type: "text", ai_enabled: true },
  { field_name: "notes", field_type: "textarea", ai_enabled: true },
  { field_name: "agenda", field_type: "list", ai_enabled: true },
  { field_name: "venue", field_type: "text", ai_enabled: false },
  { field_name: "date", field_type: "date", ai_enabled: true },
  { field_name: "summary", field_type: "textarea", ai_enabled: true },
  { field_name: "long", field_type: "textarea", ai_enabled: true },
];
const values = {
  title: "meeting on budjet",
  notes: rich("we discuss things"),
  agenda: ["venue", "", "food"],
  venue: "Room 1",
  date: "2026-10-14",
  summary: rich("   "),
  long: rich("x".repeat(11)),
};

test("rewrite-all targets filled AI fields and skips the rest", () => {
  const plan = planRewriteAll(fields, values, "formal", 5000, measureFor);
  assert.deepEqual(
    plan.targets.map((t) => [t.fieldName, t.kind, t.text]),
    [
      ["title", "text", "meeting on budjet"],
      ["notes", "rich", richText("we discuss things")],
      ["agenda", "list", "venue\n\nfood"],
      ["long", "rich", richText("x".repeat(11))],
    ],
  );
  // venue is not AI-enabled and date is not a text type: neither is listed.
  assert.deepEqual(plan.skipped, [{ fieldName: "summary", reason: "empty" }]);
  assert.deepEqual(plan.targets[2].value, ["venue", "", "food"]);
});

test("rewrite-all reports over-long values and skips one-line fields for Expand", () => {
  const plan = planRewriteAll(fields, values, "expand", 12, measureFor);
  assert.deepEqual(plan.targets.map((t) => t.fieldName), ["agenda", "long"]);
  assert.deepEqual(plan.skipped, [
    { fieldName: "title", reason: "notApplicable" },
    { fieldName: "notes", reason: "tooLong" },
    { fieldName: "summary", reason: "empty" },
  ]);
});

test("field values compare by content", () => {
  assert.equal(sameFieldValue(["a", "b"], ["a", "b"]), true);
  assert.equal(sameFieldValue(["a"], ["a", "b"]), false);
  assert.equal(sameFieldValue("a", ["a"]), false);
  assert.equal(sameFieldValue(undefined, ""), true);
  assert.equal(sameFieldValue(rich("a"), rich("a")), true);
  assert.equal(sameFieldValue(rich("a"), rich("b")), false);
  assert.equal(sameFieldValue(rich("a"), "a"), false);
});
