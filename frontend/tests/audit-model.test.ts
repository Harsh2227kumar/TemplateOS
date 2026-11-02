// Run with `npm test`. Admin audit log helpers (V1.7 P3).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  actionLabel,
  actorLabel,
  auditFiltersToParams,
  auditFiltersToQuery,
  dateRangeError,
  defaultFilters,
  entityLink,
  entityText,
  groupActions,
  queryToAuditFilters,
} from "../src/features/admin/audit-model.ts";

const TODAY = new Date("2026-11-01T10:00:00Z");

test("default filters: the last 30 days", () => {
  assert.deepEqual(defaultFilters(TODAY), { action: "", entityType: "", from: "2026-10-03", to: "2026-11-01", q: "", page: 1 });
});

test("filters round trip through the URL", () => {
  const filters = { action: "document.download", entityType: "document", from: "2026-10-01", to: "2026-10-31", q: "budget 100%", page: 3 };
  const query = auditFiltersToQuery(filters);
  assert.deepEqual(queryToAuditFilters(query, TODAY), filters);
  assert.equal(auditFiltersToQuery({ ...defaultFilters(TODAY) }), "from=2026-10-03&to=2026-11-01");
});

test("bad or missing query values fall back", () => {
  const parsed = queryToAuditFilters("from=yesterday&page=-2&q=  ", TODAY);
  assert.equal(parsed.from, "2026-10-03");
  assert.equal(parsed.to, "2026-11-01");
  assert.equal(parsed.page, 1);
  assert.equal(auditFiltersToParams(parsed).q, undefined);
});

test("api params", () => {
  assert.deepEqual(
    auditFiltersToParams({ action: "", entityType: "template", from: "2026-10-01", to: "2026-10-02", q: " x ", page: 2 }, 50),
    { page: 2, limit: 50, action: undefined, entity_type: "template", from: "2026-10-01", to: "2026-10-02", q: "x" },
  );
});

test("date range rules match the server", () => {
  assert.equal(dateRangeError("2026-10-01", "2026-10-01"), null);
  assert.equal(dateRangeError("", "2026-10-01"), null);
  assert.match(dateRangeError("2026-10-02", "2026-10-01") ?? "", /on or before/);
  assert.equal(dateRangeError("2025-11-01", "2026-11-01"), null); // 366 days
  assert.match(dateRangeError("2025-10-31", "2026-11-01") ?? "", /at most 366/);
  assert.equal(dateRangeError("2026-13-01", "2026-10-01"), "Enter valid dates.");
});

test("actions grouped by area, labels", () => {
  const options = [
    { action: "template.upload", label: "Template uploaded", area: "templates" },
    { action: "editor.session_open", label: "Editor opened", area: "editor" },
    { action: "template.clean", label: "Template cleaned", area: "templates" },
  ];
  const groups = groupActions(options);
  assert.deepEqual(groups.map((group) => [group.label, group.actions.length]), [["Templates", 2], ["Editor", 1]]);
  assert.equal(actionLabel("editor.session_open", options), "Editor opened");
  assert.equal(actionLabel("unknown.action", options), "unknown.action");
});

test("actor, entity text and links", () => {
  assert.equal(actorLabel({ actor_id: null, actor_email: "who@x.test" }), "who@x.test");
  assert.equal(actorLabel({ actor_id: null, actor_email: null }), "System");
  assert.equal(actorLabel({ actor_id: 4, actor_email: null }), "User #4");
  assert.equal(entityLink({ entity_type: "template", entity_id: 3 }), "/templates/3");
  assert.equal(entityLink({ entity_type: "document", entity_id: 9 }), "/documents/9/preview");
  assert.equal(entityLink({ entity_type: "department", entity_id: 2 }), "/admin/organizations");
  assert.equal(entityLink({ entity_type: "user", entity_id: 2 }), null);
  assert.equal(entityLink({ entity_type: "document", entity_id: null }), null);
  assert.equal(entityText({ entity_type: "template", entity_id: 12 }), "Template #12");
  assert.equal(entityText({ entity_type: "audit_log", entity_id: null }), "Audit log");
});
