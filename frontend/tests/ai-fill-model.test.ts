// Run with `npm test`. AI fill assistant: applying proposals to the form (V1.7 P2.2).
import { test } from "node:test";
import assert from "node:assert/strict";

import { AI_FLAGS_KEY, aiFlagFor, readAiFlags, withAiFlag } from "../src/components/forms/ai-flags.ts";
import {
  applyFillProposals,
  buildFormState,
  canSend,
  examplePrompts,
  fieldOrigin,
  isBlankValue,
  nextSendBody,
  overBudget,
  plainFormValue,
  progressText,
  proposalFormValue,
  stageLabel,
  summarizeTurn,
  summaryText,
  turnLimitMessage,
  undoProposal,
  type FillProposal,
} from "../src/features/ai-fill/fill-model.ts";
import { docToPlain, emptyDoc, isRichValue, plainToDoc, richValue } from "../src/features/rich-text/rich-model.ts";

const rich = (text: string) => richValue(plainToDoc(text));
const FIELDS = [
  { field_name: "student_name", field_type: "text" },
  { field_name: "abstract", field_type: "textarea" },
  { field_name: "technologies", field_type: "list" },
  { field_name: "submission_date", field_type: "date" },
  { field_name: "team_size", field_type: "number" },
  { field_name: "signature", field_type: "signature" },
];

const proposal = (field_name: string, value: string | null, extra: Partial<FillProposal> = {}): FillProposal => ({
  field_name,
  value,
  items: null,
  confidence: "high",
  ...extra,
});

test("blank values per field type", () => {
  assert.equal(isBlankValue("text", "  "), true);
  assert.equal(isBlankValue("text", "x"), false);
  assert.equal(isBlankValue("list", []), true);
  assert.equal(isBlankValue("list", [" ", ""]), true);
  assert.equal(isBlankValue("list", ["a"]), false);
  assert.equal(isBlankValue("textarea", richValue(emptyDoc())), true);
  assert.equal(isBlankValue("textarea", rich("hello")), false);
  assert.equal(isBlankValue("date", undefined), true);
});

test("plain values match what the server stores", () => {
  assert.equal(plainFormValue("list", ["Python ", "", "OpenCV"]), '["Python","OpenCV"]');
  assert.equal(plainFormValue("list", []), "");
  assert.equal(plainFormValue("textarea", rich("one\ntwo")), "one\ntwo");
  assert.equal(plainFormValue("text", "Harsh"), "Harsh");
  assert.equal(plainFormValue("number", null), "");
});

test("origin is derived from the value and the ai_fill flag", () => {
  let flags = withAiFlag({}, "student_name", "ai_fill", "Harsh Kumar");
  assert.equal(fieldOrigin("text", "", flags, "student_name"), "empty");
  assert.equal(fieldOrigin("text", "Harsh Kumar", flags, "student_name"), "ai");
  // edited by hand: no longer the AI's value
  assert.equal(fieldOrigin("text", "Harsh Kumar Singh", flags, "student_name"), "user");
  // a per-field AI style the user chose makes it theirs too
  flags = withAiFlag(flags, "student_name", "formal", "Harsh Kumar");
  assert.equal(fieldOrigin("text", "Harsh Kumar", flags, "student_name"), "user");
  assert.equal(fieldOrigin("text", "typed", {}, "student_name"), "user");

  const value = rich("An abstract.");
  flags = withAiFlag({}, "abstract", "ai_fill", value);
  assert.equal(fieldOrigin("textarea", rich("An abstract."), flags, "abstract"), "ai");
  assert.equal(fieldOrigin("textarea", rich("An abstract. More."), flags, "abstract"), "user");
});

test("form state skips signatures and sends unlocked fields as ai", () => {
  const values = {
    student_name: "Harsh",
    abstract: rich("Filled by AI."),
    technologies: ["Python", "OpenCV"],
    submission_date: "",
    team_size: "4",
    signature: "data:image/png;base64,xxx",
    [AI_FLAGS_KEY]: withAiFlag({}, "abstract", "ai_fill", rich("Filled by AI.")),
  };
  const state = buildFormState(FIELDS, values, new Set(["team_size"]));
  assert.deepEqual(state, [
    { field_name: "student_name", value: "Harsh", origin: "user" },
    { field_name: "abstract", value: "Filled by AI.", origin: "ai" },
    { field_name: "technologies", value: '["Python","OpenCV"]', origin: "user" },
    { field_name: "submission_date", value: "", origin: "empty" },
    { field_name: "team_size", value: "4", origin: "ai" }, // "Let AI update"
  ]);
});

test("proposal values become form values of the field type", () => {
  assert.deepEqual(proposalFormValue("list", { ...proposal("t", null), items: ["Python", " ", "OpenCV "] }), [
    "Python",
    "OpenCV",
  ]);
  assert.deepEqual(proposalFormValue("list", proposal("t", "Python\nOpenCV")), ["Python", "OpenCV"]);
  assert.equal(proposalFormValue("list", { ...proposal("t", null), items: [] }), null);
  const value = proposalFormValue("textarea", proposal("a", "Line one.\nLine two."));
  assert.ok(isRichValue(value));
  assert.equal(docToPlain(value.doc), "Line one.\nLine two.");
  assert.equal(proposalFormValue("date", proposal("d", " 2026-04-03 ")), "2026-04-03");
  assert.equal(proposalFormValue("text", proposal("s", "Harsh Kumar")), "Harsh Kumar");
  assert.equal(proposalFormValue("text", proposal("s", "   ")), null);
});

test("applying proposals fills empty and AI fields, never the user's", () => {
  const values = {
    student_name: "typed by me",
    abstract: richValue(emptyDoc()),
    technologies: [],
    submission_date: "",
    team_size: "3",
    signature: "",
    [AI_FLAGS_KEY]: withAiFlag({}, "team_size", "ai_fill", "3"),
  };
  const result = applyFillProposals(FIELDS, values, [
    proposal("student_name", "Harsh Kumar"),
    proposal("abstract", "This project marks attendance.", { confidence: "medium" }),
    { ...proposal("technologies", null), items: ["Python", "OpenCV"] },
    proposal("submission_date", "2026-04-03"),
    proposal("team_size", "4"),
    proposal("signature", "Harsh"),
    proposal("unknown_field", "x"),
    proposal("guessed", "y", { confidence: "low" }),
  ]);

  assert.deepEqual(result.applied, ["abstract", "technologies", "submission_date", "team_size"]);
  assert.deepEqual(result.skippedLocked, ["student_name"]);
  assert.equal(result.values.student_name, "typed by me");
  assert.deepEqual(result.values.technologies, ["Python", "OpenCV"]);
  assert.equal(result.values.team_size, "4");
  assert.equal(result.previous.team_size, "3");
  assert.deepEqual(result.previous.technologies, []);
  // the input object is untouched
  assert.equal(values.team_size, "3");

  const flags = readAiFlags(result.values);
  for (const name of result.applied) {
    assert.equal(aiFlagFor(flags, name, result.values[name]).ai_action, "ai_fill", name);
    assert.equal(fieldOrigin(FIELDS.find((f) => f.field_name === name)!.field_type, result.values[name], flags, name), "ai");
  }
  assert.equal(aiFlagFor(flags, "student_name", "typed by me").ai_modified, false);
});

test("an unlocked field accepts the proposal", () => {
  const values = { student_name: "typed by me", [AI_FLAGS_KEY]: {} };
  const result = applyFillProposals(FIELDS, values, [proposal("student_name", "Harsh Kumar")], new Set(["student_name"]));
  assert.deepEqual(result.applied, ["student_name"]);
  assert.equal(result.values.student_name, "Harsh Kumar");
  assert.equal(result.previous.student_name, "typed by me");
});

test("undo restores the earlier value and drops the flag", () => {
  const before = { student_name: "", [AI_FLAGS_KEY]: {} };
  const applied = applyFillProposals(FIELDS, before, [proposal("student_name", "Harsh Kumar")]);
  const undone = undoProposal(applied.values, "student_name", applied.previous.student_name);
  assert.equal(undone.student_name, "");
  assert.deepEqual(readAiFlags(undone), {});
});

test("turn summary and labels", () => {
  const summary = summarizeTurn({
    proposals: [proposal("a", "1"), proposal("b", "2", { confidence: "medium" }), proposal("c", "3", { confidence: "low" })],
    questions: [{}, {}],
  });
  assert.deepEqual(summary, { filled: 2, check: 1, questions: 2 });
  assert.equal(summaryText(summary), "Filled 2 · Check 1 · 2 questions");
  assert.equal(summaryText({ filled: 0, check: 0, questions: 1 }), "1 question");
  assert.equal(summaryText({ filled: 0, check: 0, questions: 0 }), "");
  assert.equal(stageLabel("asking"), "Asking a few questions");
  assert.equal(stageLabel("filling"), "Filling the form");
  assert.equal(stageLabel("ready"), "Ready");
  assert.equal(stageLabel(null), "Tell me about your document");
  assert.equal(progressText(7, 10), "Required: 7 of 10 filled");
  assert.equal(progressText(0, 0), "No required fields");
});

test("the next message carries choices, text-only answers and skipped questions", () => {
  const open = [
    { id: "t1-q1", field_names: ["submission_date"] },
    { id: "t1-q2", field_names: ["guide_name"] },
    { id: "t1-q3", field_names: ["academic_year"] },
  ];
  const body = nextSendBody("  dr rakesh mehta ", open, { "t1-q1": "3 April 2026" }, new Set(["t1-q3"]), []);
  assert.deepEqual(body, {
    message: "dr rakesh mehta",
    answers: [
      { question_id: "t1-q1", choice: "3 April 2026" },
      { question_id: "t1-q2", choice: null },
    ],
    skipped: ["t1-q3"],
    form_state: [],
  });
  // only a clicked choice: questions without an answer are not sent
  assert.deepEqual(nextSendBody("", open, { "t1-q1": "3 April 2026" }, new Set(), []).answers, [
    { question_id: "t1-q1", choice: "3 April 2026" },
  ]);
  assert.equal(canSend("", open, {}, new Set()), false);
  assert.equal(canSend("  ", open, { "t1-q3": "2025-26" }, new Set(["t1-q3"])), false); // skipped
  assert.equal(canSend("", open, { "t1-q1": "3 April 2026" }, new Set()), true);
  assert.equal(canSend("hi", [], {}, new Set()), true);
});

test("budget use of the current value", () => {
  const chars = { budget: 10, unit: "chars" as const, item_budget: null };
  assert.equal(overBudget("text", "short", chars), null);
  assert.deepEqual(overBudget("textarea", rich("x".repeat(12)), chars), { length: 12, budget: 10, unit: "chars" });
  const items = { budget: 2, unit: "items" as const, item_budget: 5 };
  assert.equal(overBudget("list", ["a", "b"], items), null);
  assert.deepEqual(overBudget("list", ["a", "b", "c"], items), { length: 3, budget: 2, unit: "items" });
  assert.deepEqual(overBudget("list", ["toolong"], items), { length: 7, budget: 5, unit: "chars" });
  assert.equal(overBudget("text", "anything", null), null);
});

test("example prompts use the first required labels", () => {
  const prompts = examplePrompts([
    { field_name: "student_name", field_label: "Student Name", is_required: true, field_type: "text" },
    { field_name: "sign", field_label: "Signature", is_required: true, field_type: "signature" },
    { field_name: "roll_number", field_label: null, is_required: true, field_type: "text" },
    { field_name: "notes", field_label: "Notes", is_required: false, field_type: "textarea" },
  ]);
  assert.equal(prompts.length, 3);
  assert.equal(prompts[1], "My student name is …, the roll number is …");
  assert.equal(examplePrompts([]).length, 2);
});

test("turn limit errors are recognised", () => {
  assert.equal(
    turnLimitMessage({ status: 409, detail: { code: "turn_limit", detail: "Clear the chat." } }),
    "Clear the chat.",
  );
  assert.equal(turnLimitMessage({ status: 409, detail: { code: "manual_edits" } }), null);
  assert.equal(turnLimitMessage({ status: 503, detail: "AI is unavailable" }), null);
  assert.equal(turnLimitMessage(null), null);
});
