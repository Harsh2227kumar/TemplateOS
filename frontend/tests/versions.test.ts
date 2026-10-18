// Run with `npm test`. Version history labels and states (V1.7 P2).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  changedFieldsText,
  FILE_MISSING_NOTE,
  NO_PDF_NOTE,
  NOT_EDITABLE_RESTORE,
  PRUNED_NOTE,
  restoreConfirmText,
  restoreErrorMessage,
  versionDownloadErrorMessage,
  versionDownloadState,
  versionLabel,
  versionMeta,
  versionPdfLabel,
} from "../src/features/document-versions/version-model.ts";
import { versionCreatedText } from "../src/features/documents/generation.ts";
import type { DocumentVersion } from "../src/lib/api/types.ts";

const version = (overrides: Partial<DocumentVersion> = {}): DocumentVersion => ({
  version: 3,
  created_at: "2026-10-18T10:00:00",
  created_by_name: "Priya",
  template_version: 2,
  pdf_status: "converted",
  pdf_error: null,
  has_docx: true,
  has_pdf: true,
  files_pruned: false,
  changed_fields: ["discussion", "venue"],
  is_latest: true,
  docx_url: "/api/v1/documents/1/versions/3/download/docx",
  pdf_url: "/api/v1/documents/1/versions/3/download/pdf",
  ...overrides,
});

test("row labels", () => {
  assert.equal(versionLabel(version()), "v3");
  assert.equal(versionMeta(version(), "2 hours ago"), "v3 · 2 hours ago · by Priya");
  assert.equal(versionMeta(version({ created_by_name: "Deleted user" }), ""), "v3 · by Deleted user");
  const labels: Record<string, string> = { discussion: "Discussion", venue: "Venue" };
  assert.equal(changedFieldsText(version(), (name) => labels[name] ?? name), "Changed: Discussion, Venue");
  assert.equal(changedFieldsText(version({ changed_fields: ["x"] })), "Changed: x");
  assert.equal(changedFieldsText(version({ changed_fields: [] })), "No value changes");
  assert.equal(changedFieldsText(version({ version: 1, changed_fields: [] })), "First version");
});

test("PDF state labels", () => {
  assert.equal(versionPdfLabel(version()), "PDF ready");
  assert.equal(versionPdfLabel(version({ has_pdf: false, pdf_status: "failed" })), "PDF failed");
  assert.equal(versionPdfLabel(version({ has_pdf: false, pdf_status: "pending" })), "PDF pending");
  assert.equal(versionPdfLabel(version({ has_pdf: false, pdf_status: null })), "No PDF");
  assert.equal(versionPdfLabel(version({ files_pruned: true, has_pdf: false })), "Files removed");
});

test("downloads: pruned, missing and no-PDF versions are explained", () => {
  assert.deepEqual(versionDownloadState(version(), "docx"), { enabled: true, reason: null });
  assert.deepEqual(versionDownloadState(version(), "pdf"), { enabled: true, reason: null });
  const pruned = version({ files_pruned: true, has_docx: false, has_pdf: false });
  assert.deepEqual(versionDownloadState(pruned, "docx"), { enabled: false, reason: PRUNED_NOTE });
  assert.deepEqual(versionDownloadState(pruned, "pdf"), { enabled: false, reason: PRUNED_NOTE });
  assert.deepEqual(versionDownloadState(version({ has_docx: false }), "docx"), { enabled: false, reason: FILE_MISSING_NOTE });
  assert.deepEqual(versionDownloadState(version({ has_pdf: false, pdf_status: "failed" }), "pdf"), {
    enabled: false,
    reason: NO_PDF_NOTE,
  });
  assert.deepEqual(versionDownloadState(version({ has_pdf: false, pdf_status: "converted" }), "pdf"), {
    enabled: false,
    reason: FILE_MISSING_NOTE,
  });
});

test("messages", () => {
  assert.equal(restoreConfirmText(version({ version: 1 })), "Replace the current values with v1? Unsaved changes will be lost.");
  assert.match(versionDownloadErrorMessage(410, "docx"), /no longer on the server/);
  assert.equal(versionDownloadErrorMessage(409, "pdf"), "No PDF for this version.");
  assert.equal(versionDownloadErrorMessage(404, "docx"), "This version no longer exists.");
  assert.equal(versionDownloadErrorMessage(500, "docx", "Server error"), "Server error");
  assert.equal(restoreErrorMessage(409), NOT_EDITABLE_RESTORE);
  assert.equal(restoreErrorMessage(undefined), "Restore failed. Please try again.");
  assert.equal(versionCreatedText({ version: 3 }), "Version 3 created");
  assert.equal(versionCreatedText({ version: null }), null);
});
