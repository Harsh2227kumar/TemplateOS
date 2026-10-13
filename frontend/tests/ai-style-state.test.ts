// Run with `npm test` (node --test; Node >= 22.18 strips TypeScript types natively).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  aiStyleReducer,
  initialAiStyleState,
  normalizeAiResult,
  planAiAction,
  type AiStyle,
  type AiStyleState,
} from "../src/components/fields/ai-style-state.ts";

const MAX = 5000;
let seq = 0;

/**
 * Simulates what the hook does for one click: plan, then either apply the
 * cached result or run a (fake) request that returns `reply(source)`.
 * Returns the new state and the new field text.
 */
function click(
  state: AiStyleState,
  field: string,
  style: AiStyle,
  reply: (source: string, style: AiStyle) => string,
): { state: AiStyleState; field: string; fetched: boolean; sentText?: string } {
  const plan = planAiAction(state, style, field, MAX);
  if (plan.kind === "cached") {
    const next = aiStyleReducer(state, { type: "applyCached", style, source: plan.source, text: plan.text });
    return { state: aiStyleReducer(next, { type: "fieldChanged", fieldText: plan.text }), field: plan.text, fetched: false };
  }
  if (plan.kind !== "fetch") return { state, field, fetched: false };
  const requestId = ++seq;
  let s = aiStyleReducer(state, { type: "request", style, requestId, source: plan.source, fieldText: field });
  const text = reply(plan.source, style);
  s = aiStyleReducer(s, { type: "success", requestId, text });
  s = aiStyleReducer(s, { type: "fieldChanged", fieldText: text });
  return { state: s, field: text, fetched: true, sentText: plan.source };
}

const fakeAi = (source: string, style: AiStyle) => `[${style}] ${source}`;

test("user text -> Formal -> Concise -> Undo -> edit -> Formal", () => {
  let state = initialAiStyleState;
  let field = "pls send the report asap";
  state = aiStyleReducer(state, { type: "fieldChanged", fieldText: field });

  // Formal: based on the user's text.
  let r = click(state, field, "formal", fakeAi);
  assert.equal(r.sentText, "pls send the report asap");
  assert.equal(r.field, "[formal] pls send the report asap");
  assert.equal(r.state.applied?.style, "formal");
  assert.equal(r.state.base, "pls send the report asap");
  ({ state, field } = r);

  // Concise: still based on the USER's text, not the formal result.
  r = click(state, field, "concise", fakeAi);
  assert.equal(r.sentText, "pls send the report asap");
  assert.equal(r.field, "[concise] pls send the report asap");
  assert.equal(r.state.applied?.style, "concise");
  ({ state, field } = r);

  // Back to Formal: served from cache, no new request.
  r = click(state, field, "formal", fakeAi);
  assert.equal(r.fetched, false);
  assert.equal(r.field, "[formal] pls send the report asap");
  ({ state, field } = r);

  // Undo (Original) after several actions: back to the user's own text.
  assert.equal(state.base, "pls send the report asap");
  field = state.base!;
  state = aiStyleReducer(state, { type: "revert" });
  state = aiStyleReducer(state, { type: "fieldChanged", fieldText: field });
  assert.equal(field, "pls send the report asap");
  assert.equal(state.applied, null);
  assert.equal(state.base, null);

  // The user edits the text: it becomes the new original.
  field = "please send the final report by Friday";
  state = aiStyleReducer(state, { type: "fieldChanged", fieldText: field });

  // Formal again: a fresh request based on the edited text (old cache unused).
  r = click(state, field, "formal", fakeAi);
  assert.equal(r.fetched, true);
  assert.equal(r.sentText, "please send the final report by Friday");
  assert.equal(r.field, "[formal] please send the final report by Friday");
});

test("editing an AI result makes the edit the new base", () => {
  let state = initialAiStyleState;
  let r = click(state, "hello", "formal", fakeAi);
  state = r.state;
  const edited = r.field + " (tweaked)";
  state = aiStyleReducer(state, { type: "fieldChanged", fieldText: edited });
  assert.equal(state.applied, null);
  r = click(state, edited, "concise", fakeAi);
  assert.equal(r.sentText, edited);
});

test("clicking the active style asks for a new version from the original", () => {
  let state = initialAiStyleState;
  let r = click(state, "hi there", "tone", fakeAi);
  state = r.state;
  const plan = planAiAction(state, "tone", r.field, MAX);
  assert.deepEqual(plan, { kind: "fetch", source: "hi there" });
});

test("a second click while a request runs is ignored", () => {
  let state = aiStyleReducer(initialAiStyleState, {
    type: "request",
    style: "formal",
    requestId: 1,
    source: "x",
    fieldText: "x",
  });
  assert.deepEqual(planAiAction(state, "concise", "x", MAX), { kind: "busy" });
  const again = aiStyleReducer(state, { type: "request", style: "concise", requestId: 2, source: "x", fieldText: "x" });
  assert.equal(again.pending?.requestId, 1);
});

test("a form reset during a request drops it, and its late result is ignored", () => {
  let state = aiStyleReducer(initialAiStyleState, {
    type: "request",
    style: "formal",
    requestId: 7,
    source: "draft",
    fieldText: "draft",
  });
  state = aiStyleReducer(state, { type: "fieldChanged", fieldText: "last saved value" });
  assert.equal(state.pending, null);
  const after = aiStyleReducer(state, { type: "success", requestId: 7, text: "late" });
  assert.equal(after.applied, null);
});

test("failure keeps the previous style and text", () => {
  let r = click(initialAiStyleState, "abc", "formal", fakeAi);
  let state = aiStyleReducer(r.state, { type: "request", style: "concise", requestId: 99, source: "abc", fieldText: r.field });
  state = aiStyleReducer(state, { type: "failure", requestId: 99 });
  assert.equal(state.pending, null);
  assert.equal(state.applied?.style, "formal");
  assert.equal(state.base, "abc");
});

test("empty and over-limit text are not sent", () => {
  assert.deepEqual(planAiAction(initialAiStyleState, "formal", "   ", MAX), { kind: "empty" });
  const long = "a".repeat(MAX + 1);
  assert.deepEqual(planAiAction(initialAiStyleState, "formal", long, MAX), { kind: "tooLong", length: MAX + 1 });
});

test("the limit applies to the original text, not the AI result", () => {
  const r = click(initialAiStyleState, "short", "formal", () => "x".repeat(MAX + 10));
  assert.equal(planAiAction(r.state, "concise", r.field, MAX).kind, "fetch");
});

test("reset clears everything", () => {
  const r = click(initialAiStyleState, "abc", "formal", fakeAi);
  assert.deepEqual(aiStyleReducer(r.state, { type: "reset" }), initialAiStyleState);
});

test("single-line fields get newlines collapsed", () => {
  assert.equal(normalizeAiResult("Line one.\n\nLine two.\n", false), "Line one. Line two.");
  assert.equal(normalizeAiResult("Line one.\r\nLine two.\n", true), "Line one.\nLine two.");
});
