// Run with `npm test`. The API sends naive UTC timestamps (no "Z").
import { test } from "node:test";
import assert from "node:assert/strict";

import { parseServerDate, serverTime } from "../src/lib/dates.ts";

test("naive API timestamps are read as UTC, not local time", () => {
  assert.equal(parseServerDate("2026-10-13T10:21:05")?.toISOString(), "2026-10-13T10:21:05.000Z");
  assert.equal(parseServerDate("2026-10-13T10:21:05.123456")?.toISOString(), "2026-10-13T10:21:05.123Z");
  assert.equal(parseServerDate("2026-10-13 10:21:05")?.toISOString(), "2026-10-13T10:21:05.000Z");
});

test("timestamps that already carry a zone are left alone", () => {
  assert.equal(parseServerDate("2026-10-13T10:21:05Z")?.toISOString(), "2026-10-13T10:21:05.000Z");
  assert.equal(parseServerDate("2026-10-13T15:51:05+05:30")?.toISOString(), "2026-10-13T10:21:05.000Z");
});

test("missing or invalid values give null / 0", () => {
  assert.equal(parseServerDate(null), null);
  assert.equal(parseServerDate(""), null);
  assert.equal(parseServerDate("not a date"), null);
  assert.equal(serverTime(undefined), 0);
  assert.ok(serverTime("2026-10-13T10:21:05") > serverTime("2026-10-13T10:20:05"));
});
