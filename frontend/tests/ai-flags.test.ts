// Run with `npm test`. AI provenance flags (V1.7 P2 ai_modified / ai_action).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  AI_FLAGS_KEY,
  aiFingerprint,
  aiFlagFor,
  carryAiFlags,
  readAiFlags,
  savedAiFlags,
  withAiFlag,
  withoutAiFlag,
} from "../src/components/forms/ai-flags.ts";
import { plainToDoc, richValue } from "../src/features/rich-text/rich-model.ts";

const rich = (text: string) => richValue(plainToDoc(text));

test("fingerprints tell field values apart", () => {
  assert.equal(aiFingerprint("Hello"), aiFingerprint("Hello"));
  assert.notEqual(aiFingerprint("Hello"), aiFingerprint("Hello "));
  assert.equal(aiFingerprint(["a", " ", "b "]), aiFingerprint(["a", "b"])); // as stored
  assert.notEqual(aiFingerprint(["a", "b"]), aiFingerprint("a\nb"));
  assert.equal(aiFingerprint(rich("x")), aiFingerprint(rich("x")));
  assert.notEqual(aiFingerprint(rich("x")), aiFingerprint(rich("y")));
  assert.equal(aiFingerprint(undefined), aiFingerprint(""));
});

test("apply -> edit -> revert -> reset", () => {
  const original = rich("we discuss things");
  const formal = rich("We discussed the matters.");
  // Applying a style marks the field.
  let flags = withAiFlag({}, "notes", "formal", formal);
  assert.deepEqual(aiFlagFor(flags, "notes", formal), { ai_modified: true, ai_action: "formal" });
  // A manual edit (any other value) is no longer AI-written.
  assert.deepEqual(aiFlagFor(flags, "notes", rich("We discussed the matters!")), { ai_modified: false, ai_action: null });
  // Undoing the edit (back to the AI text) shows it as AI-written again.
  assert.equal(aiFlagFor(flags, "notes", formal).ai_modified, true);
  // "Original" removes the flag.
  flags = withoutAiFlag(flags, "notes");
  assert.equal(aiFlagFor(flags, "notes", original).ai_modified, false);
  assert.equal(withoutAiFlag(flags, "missing"), flags);
  // Another style replaces the action.
  flags = withAiFlag(withAiFlag({}, "notes", "formal", formal), "notes", "concise", rich("Discussed."));
  assert.deepEqual(aiFlagFor(flags, "notes", rich("Discussed.")), { ai_modified: true, ai_action: "concise" });
});

test("saved flags come back with the saved values (prefill, Reset Form, restore)", () => {
  const values = { title: "Budget Review", notes: rich("Formal text"), agenda: ["One", "Two"] };
  const flags = savedAiFlags(
    [
      { field_name: "title", ai_modified: true, ai_action: "grammar" },
      { field_name: "notes", ai_modified: true, ai_action: "formal" },
      { field_name: "agenda", ai_modified: false, ai_action: null },
      { field_name: "gone", ai_modified: true, ai_action: "tone" },
      { field_name: "broken", ai_modified: true, ai_action: null },
    ],
    values,
  );
  assert.deepEqual(Object.keys(flags).sort(), ["notes", "title"]);
  assert.deepEqual(aiFlagFor(flags, "title", "Budget Review"), { ai_modified: true, ai_action: "grammar" });
  assert.equal(aiFlagFor(flags, "agenda", values.agenda).ai_modified, false);
  assert.deepEqual(readAiFlags({ ...values, [AI_FLAGS_KEY]: flags }), flags);
  assert.deepEqual(readAiFlags({}), {});
  assert.deepEqual(readAiFlags({ [AI_FLAGS_KEY]: "nope" }), {});
});

test("flags survive a save that normalizes the values", () => {
  const before = { agenda: ["  One", "", "Two "], title: "Edited by hand" };
  const after = { agenda: ["One", "Two"], title: "Edited by hand" };
  const flags = withAiFlag(withAiFlag({}, "agenda", "expand", before.agenda), "title", "tone", "AI title");
  const carried = carryAiFlags(flags, before, after);
  assert.deepEqual(aiFlagFor(carried, "agenda", after.agenda), { ai_modified: true, ai_action: "expand" });
  assert.equal("title" in carried, false); // edited after AI: dropped
});
