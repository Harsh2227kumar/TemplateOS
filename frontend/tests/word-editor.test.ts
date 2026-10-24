// Run with `npm test`. Word file editor rules and labels (V1.7 P2.1).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  isFinal,
  nextPollDelay,
  openErrorMessage,
  sessionMessage,
} from "../src/features/word-editor/save-status.ts";
import {
  canEditDocumentFile,
  copyBadgeText,
  documentEditorPath,
  manualEditsConflict,
  templateEditorActions,
} from "../src/features/word-editor/word-editor-model.ts";
import {
  fieldChangesSummary,
  placeholderText,
  revisionChangeText,
  revisionSourceLabel,
} from "../src/features/word-editor/editor-review-model.ts";
import { docsApiScriptUrl } from "../src/features/word-editor/load-docs-api.ts";
import { changedFieldsText, manualEditLabel } from "../src/features/document-versions/version-model.ts";
import { templateKeys, wordEditorKeys, keyStartsWith } from "../src/lib/query/keys.ts";
import type { FieldChanges } from "../src/lib/api/types.ts";

const session = (status: Parameters<typeof isFinal>[0], extra: Record<string, unknown> = {}) => ({
  status,
  result_revision: null,
  result_version: null,
  error: null,
  ...extra,
});

test("save status: final states and messages", () => {
  assert.equal(isFinal("open"), false);
  assert.equal(isFinal("saving"), false);
  for (const status of ["saved", "failed", "closed", "expired"] as const) assert.equal(isFinal(status), true);

  assert.equal(sessionMessage(session("saving"), "document"), "Saving your changes…");
  assert.equal(sessionMessage(session("saved", { result_revision: 4 }), "template"), "Saved as revision 4.");
  assert.equal(
    sessionMessage(session("saved", { result_version: 3 }), "document"),
    "Version 3 saved (edited manually).",
  );
  assert.equal(sessionMessage(session("closed"), "document"), "No changes were made.");
  assert.equal(sessionMessage(session("failed", { error: "Not a Word file" }), "template"), "Saving failed: Not a Word file");
  assert.match(sessionMessage(session("expired"), "template"), /expired/);
});

test("save status: 1 s then 2 s backoff", () => {
  assert.deepEqual([0, 1, 4, 5, 20].map(nextPollDelay), [1000, 1000, 1000, 2000, 2000]);
});

test("open errors by status", () => {
  assert.equal(openErrorMessage(503), "The document editor is not available.");
  assert.equal(openErrorMessage(409, "Being edited by Priya since 10:15"), "Being edited by Priya since 10:15");
  assert.equal(openErrorMessage(410), "This version's files were removed.");
  assert.match(openErrorMessage(undefined), /could not be opened/);
});

const template = (overrides: Partial<Parameters<typeof templateEditorActions>[0]> = {}) => ({
  can_manage: false,
  is_personal_copy: false,
  visibility: "organization",
  original_file_path: "templates/original/a.docx",
  ...overrides,
});

test("entry points: editor flag x manager x personal copy", () => {
  assert.deepEqual(templateEditorActions(template({ can_manage: true }), false), {
    customize: false,
    editFile: false,
    confirmEdit: false,
  });
  // A viewer can only customize.
  assert.deepEqual(templateEditorActions(template(), true), { customize: true, editFile: false, confirmEdit: false });
  // A manager of a shared original edits after a warning, and can still customize.
  assert.deepEqual(templateEditorActions(template({ can_manage: true }), true), {
    customize: true,
    editFile: true,
    confirmEdit: true,
  });
  // My own private template: no warning.
  assert.equal(templateEditorActions(template({ can_manage: true, visibility: "private" }), true).confirmEdit, false);
  // My personal copy: edit without warning, no copy of the copy.
  assert.deepEqual(templateEditorActions(template({ can_manage: true, is_personal_copy: true, visibility: "private" }), true), {
    customize: false,
    editFile: true,
    confirmEdit: false,
  });
});

test("entry points: document editable x has docx", () => {
  assert.equal(canEditDocumentFile({ editorEnabled: true, documentStatus: "generated", hasDocx: true }), true);
  assert.equal(canEditDocumentFile({ editorEnabled: true, documentStatus: "draft", hasDocx: true }), true);
  assert.equal(canEditDocumentFile({ editorEnabled: false, documentStatus: "generated", hasDocx: true }), false);
  assert.equal(canEditDocumentFile({ editorEnabled: true, documentStatus: "archived", hasDocx: true }), false);
  assert.equal(canEditDocumentFile({ editorEnabled: true, documentStatus: "generated", hasDocx: false }), false);
  assert.equal(documentEditorPath(7), "/documents/7/edit-file");
  assert.equal(documentEditorPath(7, 3), "/documents/7/edit-file?version=3");
});

test("copy badge", () => {
  assert.equal(copyBadgeText({ is_personal_copy: false, parent_template_name: null }), null);
  assert.equal(copyBadgeText({ is_personal_copy: true, parent_template_name: "MoM" }), "My copy of MoM");
  assert.equal(copyBadgeText({ is_personal_copy: true, parent_template_name: null }), "My copy");
});

test("revision labels", () => {
  assert.equal(revisionSourceLabel("manual_edit"), "Edited in Word");
  assert.equal(revisionSourceLabel("customize"), "Copied");
  assert.equal(revisionSourceLabel("something_new"), "something_new");
  assert.equal(
    revisionChangeText({ placeholders_added: ["a", "b"], placeholders_removed: ["c"], blank_suggestions: 1 }),
    "+2 fields · −1 field · 1 blank",
  );
  assert.equal(revisionChangeText({ placeholders_added: [], placeholders_removed: [], blank_suggestions: 0 }), "");
});

const changes = (overrides: Partial<FieldChanges> = {}): FieldChanges => ({
  template_id: 1,
  revision: 3,
  added: [],
  removed: [],
  blank_suggestions: 0,
  renderable: true,
  render_error: null,
  has_changes: false,
  ...overrides,
});

test("field changes summary", () => {
  assert.equal(fieldChangesSummary(changes()).kind, "none");
  assert.equal(fieldChangesSummary(changes()).title, "No field changes. Template updated.");

  const broken = fieldChangesSummary(changes({ renderable: false, render_error: "unexpected '}'" }));
  assert.equal(broken.kind, "render_error");
  assert.deepEqual(broken.lines, ["unexpected '}'"]);

  const blanks = fieldChangesSummary(changes({ blank_suggestions: 2 }));
  assert.equal(blanks.kind, "changes");
  assert.deepEqual(blanks.lines, ["2 blanks can become fields"]);
  assert.equal(blanks.cleanFirst, true);
  assert.equal(blanks.detectNew, false);

  const added = fieldChangesSummary(
    changes({
      has_changes: true,
      added: [{ key: "date_of_meeting", suggested_label: "Date of meeting", suggested_type: "date" }],
      removed: ["venue"],
    }),
  );
  assert.deepEqual(added.lines, ["1 new field", "1 field is no longer in the file"]);
  assert.equal(added.detectNew, true);
  assert.equal(added.reviewFields, true);
  assert.equal(added.cleanFirst, false);
});

test("manual edits conflict from generate", () => {
  const detail = { detail: "The latest version (v4) was edited manually.", code: "manual_edits", version: 4 };
  assert.deepEqual(manualEditsConflict({ status: 409, detail, message: detail.detail }), {
    message: detail.detail,
    version: 4,
  });
  assert.equal(manualEditsConflict({ status: 409, detail: undefined, message: "Not editable" }), null);
  assert.equal(manualEditsConflict({ status: 422, detail }), null);
  assert.equal(manualEditsConflict(null), null);
});

test("manual-edit version labels", () => {
  assert.equal(manualEditLabel({ source: "generated", base_version: null }), null);
  assert.equal(manualEditLabel({ source: "manual_edit", base_version: 3 }), "Edited manually from v3");
  assert.equal(manualEditLabel({ source: "manual_edit", base_version: null }), "Edited manually");
  assert.equal(
    changedFieldsText({ version: 4, changed_fields: [], source: "manual_edit" }),
    "Word file edited; values unchanged",
  );
  assert.equal(changedFieldsText({ version: 4, changed_fields: [], source: "generated" }), "No value changes");
});

test("keys and helpers", () => {
  assert.ok(keyStartsWith(templateKeys.revisions(5), templateKeys.detail(5)));
  assert.ok(keyStartsWith(templateKeys.fieldChanges(5), templateKeys.detail(5)));
  assert.deepEqual(wordEditorKeys.session("abc"), ["word-editor", "session", "abc"]);
  assert.equal(placeholderText("date_of_meeting"), "{{ date_of_meeting }}");
  assert.equal(
    docsApiScriptUrl("http://localhost:8082/"),
    "http://localhost:8082/web-apps/apps/api/documents/api.js",
  );
});
