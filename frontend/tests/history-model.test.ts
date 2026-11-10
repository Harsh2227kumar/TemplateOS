// Run with `npm test`. Download history helpers (V1.7 P3).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  downloadDocumentName,
  downloadErrorMessage,
  downloadLabel,
  downloadPath,
  humanFileSize,
} from "../src/features/downloads/history-model.ts";
import { toQuery } from "../src/lib/api/query-string.ts";
import { auditKeys, historyKeys, keyStartsWith } from "../src/lib/query/keys.ts";

test("human file sizes", () => {
  assert.equal(humanFileSize(null), "");
  assert.equal(humanFileSize(-1), "");
  assert.equal(humanFileSize(512), "512 B");
  assert.equal(humanFileSize(1536), "1.5 KB");
  assert.equal(humanFileSize(820 * 1024), "820 KB");
  assert.equal(humanFileSize(1.25 * 1024 * 1024), "1.3 MB");
  assert.equal(humanFileSize(3 * 1024 ** 3), "3 GB");
});

test("download labels and deleted documents", () => {
  assert.equal(downloadLabel({ version: 2, format: "pdf", version_source: "manual_edit" }), "v2 · PDF · Edited manually");
  assert.equal(downloadLabel({ version: 1, format: "docx", version_source: "generated" }), "v1 · DOCX");
  assert.equal(downloadLabel({ version: null, format: "docx", version_source: null }), "DOCX");
  assert.equal(downloadDocumentName({ document_name: "Budget", document_exists: true }), "Budget");
  assert.equal(downloadDocumentName({ document_name: "Budget", document_exists: false }), "Budget (deleted)");
});

test("download paths", () => {
  assert.equal(downloadPath(7, "docx"), "/documents/7/download?format=docx");
  assert.equal(downloadPath(7, "pdf"), "/documents/7/download/pdf");
  assert.equal(downloadPath(7, "pdf", 3), "/documents/7/versions/3/download/pdf");
});

test("download error messages", () => {
  assert.equal(downloadErrorMessage(403), "You don't have access to this file.");
  assert.equal(downloadErrorMessage(409), "The PDF is not available yet.");
  assert.match(downloadErrorMessage(410), /removed by retention/);
  assert.equal(downloadErrorMessage(500, "Server error"), "Server error");
  assert.equal(downloadErrorMessage(undefined), "Download failed. Please try again.");
});

test("query strings and keys", () => {
  assert.equal(toQuery({}), "");
  assert.equal(toQuery({ page: 2, format: undefined, q: "", document_id: 5 }), "?page=2&document_id=5");
  assert.equal(toQuery({ q: "100% done" }), "?q=100%25+done");
  assert.deepEqual(historyKeys.myDownloads({ page: 1, format: undefined }), ["history", "mine", { page: 1 }]);
  assert.ok(keyStartsWith(historyKeys.documentDownloads(4, { page: 1 }), historyKeys.all));
  assert.ok(keyStartsWith(auditKeys.list({ action: "auth.login" }), auditKeys.lists()));
});
