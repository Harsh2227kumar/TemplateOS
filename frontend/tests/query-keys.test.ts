// Run with `npm test`. Query-key factories and the query retry policy.
import { test } from "node:test";
import assert from "node:assert/strict";

import { documentKeys, keyStartsWith, queryKeys, templateKeys } from "../src/lib/query/keys.ts";
import { errorStatus, shouldRetryQuery } from "../src/lib/query/retry.ts";

test("keys are stable: same input, equal key", () => {
  assert.deepEqual(templateKeys.detail(7), templateKeys.detail(7));
  assert.deepEqual(templateKeys.fields(7), ["templates", "detail", 7, "fields"]);
  assert.deepEqual(templateKeys.content(7), ["templates", "detail", 7, "content", "original"]);
  assert.deepEqual(templateKeys.content(7, "processed"), ["templates", "detail", 7, "content", "processed"]);
  assert.deepEqual(templateKeys.cleanSuggestions(7), ["templates", "detail", 7, "clean-suggestions"]);
  assert.deepEqual(documentKeys.detail(3), ["documents", "detail", 3]);
  assert.deepEqual(documentKeys.mine(), ["documents", "list", "mine"]);
  assert.equal(queryKeys.templates, templateKeys);
  assert.equal(queryKeys.documents, documentKeys);
});

test("empty library filters share one cache entry", () => {
  assert.deepEqual(
    templateKeys.library({ search: "", category: "", visibility: "", page: 1, limit: 20 }),
    templateKeys.library({ page: 1, limit: 20 }),
  );
  assert.notDeepEqual(
    templateKeys.library({ search: "notice", page: 1 }),
    templateKeys.library({ page: 1 }),
  );
});

test("a template's fields, content and suggestions sit under its detail key", () => {
  const detail = templateKeys.detail(5);
  assert.ok(keyStartsWith(templateKeys.fields(5), detail));
  assert.ok(keyStartsWith(templateKeys.content(5), detail));
  assert.ok(keyStartsWith(templateKeys.cleanSuggestions(5), detail));
  assert.ok(!keyStartsWith(templateKeys.fields(6), detail), "other templates are untouched");
  assert.ok(!keyStartsWith(templateKeys.detail(50), detail), "5 must not prefix-match 50");
});

test("list invalidation hits my templates and the library, not details", () => {
  const lists = templateKeys.lists();
  assert.ok(keyStartsWith(templateKeys.mine(), lists));
  assert.ok(keyStartsWith(templateKeys.library({ page: 2 }), lists));
  assert.ok(!keyStartsWith(templateKeys.detail(1), lists));
  assert.ok(!keyStartsWith(templateKeys.accessOptions(), lists));
});

test("saving a draft invalidates every documents query", () => {
  assert.ok(keyStartsWith(documentKeys.mine(), documentKeys.all));
  assert.ok(keyStartsWith(documentKeys.detail(9), documentKeys.all));
  assert.ok(!keyStartsWith(templateKeys.detail(9), documentKeys.all));
});

test("queries retry once for network errors and 5xx", () => {
  assert.equal(shouldRetryQuery(0, new TypeError("Failed to fetch")), true);
  assert.equal(shouldRetryQuery(0, { status: 503 }), true);
  assert.equal(shouldRetryQuery(1, { status: 500 }), false, "only one retry");
});

test("queries never retry a 4xx", () => {
  for (const status of [400, 401, 403, 404, 409, 422]) {
    assert.equal(shouldRetryQuery(0, { status }), false, `status ${status}`);
  }
});

test("errorStatus reads a numeric status only", () => {
  assert.equal(errorStatus({ status: 404 }), 404);
  assert.equal(errorStatus({ status: "404" }), undefined);
  assert.equal(errorStatus(null), undefined);
  assert.equal(errorStatus(new Error("x")), undefined);
});
