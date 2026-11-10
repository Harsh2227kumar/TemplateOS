// Run with `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";

import { listExampleItems } from "../src/lib/list-example.ts";

test("JSON array examples become one placeholder per item", () => {
  assert.deepEqual(listExampleItems('["Budget approval", "Venue selection"]'), ["Budget approval", "Venue selection"]);
});

test("blank and non-text items are dropped, numbers kept", () => {
  assert.deepEqual(listExampleItems('[" Venue ", "", null, 3]'), ["Venue", "3"]);
});

test("plain text is a single example item", () => {
  assert.deepEqual(listExampleItems("Venue booking"), ["Venue booking"]);
  assert.deepEqual(listExampleItems("[draft] notes"), ["[draft] notes"]);
});

test("empty examples give no placeholders", () => {
  assert.deepEqual(listExampleItems(null), []);
  assert.deepEqual(listExampleItems("  "), []);
  assert.deepEqual(listExampleItems("[]"), []);
});
