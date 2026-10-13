// Run with `npm test`. Pure helpers behind the V1.6 generate / download UI.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  fallbackDownloadFilename,
  filenameFromContentDisposition,
  generateActionLabel,
  pdfStatusLabel,
} from "../src/features/documents/generation.ts";

test("pdf status labels", () => {
  assert.equal(pdfStatusLabel("ok"), "PDF ready");
  assert.equal(pdfStatusLabel("failed"), "PDF conversion failed");
  assert.equal(pdfStatusLabel("not_configured"), "PDF conversion is not set up on the server");
  assert.equal(pdfStatusLabel(null), "Not generated yet");
  assert.equal(pdfStatusLabel(undefined), "Not generated yet");
});

test("generate action label follows generated / stale state", () => {
  assert.equal(generateActionLabel(false, false), "Generate document");
  assert.equal(generateActionLabel(false, true), "Generate document");
  assert.equal(generateActionLabel(true, false), "Regenerate");
  assert.equal(generateActionLabel(true, true), "Regenerate (values changed)");
});

test("filename from Content-Disposition prefers the UTF-8 form", () => {
  assert.equal(
    filenameFromContentDisposition(
      "attachment; filename=\"Caf_ MoM.docx\"; filename*=UTF-8''Caf%C3%A9%20MoM.docx",
    ),
    "Café MoM.docx",
  );
  assert.equal(filenameFromContentDisposition('attachment; filename="Weekly MoM 13 10.pdf"'), "Weekly MoM 13 10.pdf");
  assert.equal(filenameFromContentDisposition("attachment; filename=plain.docx"), "plain.docx");
  assert.equal(filenameFromContentDisposition('attachment; filename="a\\"b.docx"'), 'a"b.docx');
});

test("filename from a missing or odd header", () => {
  assert.equal(filenameFromContentDisposition(null), null);
  assert.equal(filenameFromContentDisposition(""), null);
  assert.equal(filenameFromContentDisposition("inline"), null);
  // Bad percent-encoding falls back to the plain filename.
  assert.equal(
    filenameFromContentDisposition("attachment; filename=\"x.docx\"; filename*=UTF-8''%E0%A4%A.docx"),
    "x.docx",
  );
  // Path separators never survive.
  assert.equal(filenameFromContentDisposition('attachment; filename="../../evil.docx"'), ".._.._evil.docx");
});

test("fallback filename mirrors the backend rule", () => {
  assert.equal(fallbackDownloadFilename("Weekly MoM: 13/10 <final>?", 7, "docx"), "Weekly MoM 13 10 final.docx");
  assert.equal(fallbackDownloadFilename("Café notes", 7, "pdf"), "Café notes.pdf");
  assert.equal(fallbackDownloadFilename("///", 7, "pdf"), "document-7.pdf");
  assert.equal(fallbackDownloadFilename(null, 12, "docx"), "document-12.docx");
  assert.equal(fallbackDownloadFilename("x".repeat(150), 1, "docx"), `${"x".repeat(100)}.docx`);
});
