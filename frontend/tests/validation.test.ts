// Run with `npm test`. Messages must match backend/app/services/document_validator.py.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildFormSchema,
  describeValidationRule,
  parseValidationRule,
  validateFieldValue,
} from "../src/lib/validation.ts";

const f = (field_type: string, is_required = false, validation_rule: string | null = null) => ({
  field_type,
  is_required,
  validation_rule,
});

test("parses rules like the backend, ignoring malformed parts", () => {
  assert.deepEqual(parseValidationRule("email|min:5"), { email: true, min: 5 });
  assert.deepEqual(parseValidationRule("min:abc|max:10"), { max: 10 });
  assert.deepEqual(parseValidationRule(null), {});
});

test("required: whitespace and blank list items count as empty", () => {
  assert.equal(validateFieldValue(f("text", true), "   "), "This field is required");
  assert.equal(validateFieldValue(f("list", true), ["", "  "]), "This field is required");
  assert.equal(validateFieldValue(f("list", true), ["a"]), null);
  assert.equal(validateFieldValue(f("text", false), ""), null);
  assert.equal(validateFieldValue(f("list", false), undefined), null);
});

test("numbers must be finite and respect min/max by value", () => {
  assert.equal(validateFieldValue(f("number"), "abc"), "Must be a valid number");
  assert.equal(validateFieldValue(f("number"), "Infinity"), "Must be a valid number");
  assert.equal(validateFieldValue(f("number", false, "min:1|max:10"), "0"), "Must be at least 1");
  assert.equal(validateFieldValue(f("number", false, "min:1|max:10"), "11"), "Must be at most 10");
  assert.equal(validateFieldValue(f("number", false, "min:1|max:10"), "2.5"), null);
});

test("email rule applies to text fields too", () => {
  assert.equal(validateFieldValue(f("text", false, "email"), "nope"), "Must be a valid email address");
  assert.equal(validateFieldValue(f("email"), "a@b.co"), null);
});

test("text length and list item counts", () => {
  assert.equal(validateFieldValue(f("textarea", false, "max:3"), "abcd"), "Must be at most 3 characters");
  assert.equal(validateFieldValue(f("text", false, "min:3"), "ab"), "Must be at least 3 characters");
  assert.equal(validateFieldValue(f("list", false, "min:2"), ["a", ""]), "Must have at least 2 items");
  assert.equal(validateFieldValue(f("list", false, "max:1"), ["a", "b"]), "Must have at most 1 items");
});

test("dates must be real calendar dates", () => {
  assert.equal(validateFieldValue(f("date"), "2025-02-30"), "Must be a valid date");
  assert.equal(validateFieldValue(f("date"), "2025-02-28"), null);
});

test("schema reports one message per field", () => {
  const schema = buildFormSchema([{ field_name: "n", ...f("number", true) }]);
  const result = schema.safeParse({ n: "" });
  assert.equal(result.success, false);
  if (!result.success) {
    assert.equal(result.error.issues.length, 1);
    assert.equal(result.error.issues[0].message, "This field is required");
  }
});

test("rule hints", () => {
  assert.equal(describeValidationRule(f("list", false, "min:2|max:5")), "2–5 items");
  assert.equal(describeValidationRule(f("number", false, "max:100")), "At most 100");
  assert.equal(describeValidationRule(f("text")), null);
});
