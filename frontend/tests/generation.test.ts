// Run with `npm test`. Pure helpers behind the V1.6 generate / download UI.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EARLIER_PDF_NOTE,
  fallbackDownloadFilename,
  filenameFromContentDisposition,
  generateActionLabel,
  generateSuccessMessage,
  markPdfFailed,
  PDF_FILE_MISSING_MESSAGE,
  pdfRowView,
  pdfStatusLabel,
  quickDownloadFormat,
  SLOW_PDF_HINT,
  SLOW_PDF_HINT_MS,
  startSlowHintTimer,
  type PdfState,
} from "../src/features/documents/generation.ts";

test("pdf status labels", () => {
  assert.equal(pdfStatusLabel("converted"), "PDF ready");
  assert.equal(pdfStatusLabel("failed"), "PDF not available");
  assert.equal(pdfStatusLabel("pending"), "PDF conversion did not finish.");
  assert.equal(pdfStatusLabel(null), "Not generated yet");
  assert.equal(pdfStatusLabel(undefined), "Not generated yet");
});

const idle = { generating: false, retrying: false };
const converted: PdfState = {
  pdf_status: "converted",
  pdf_error: null,
  pdf_filename: "minutes-1a2b.pdf",
  has_pdf: true,
};
const failed: PdfState = {
  pdf_status: "failed",
  pdf_error: "PDF service is not reachable at http://localhost:3000. Is Gotenberg running?",
  pdf_filename: null,
  has_pdf: false,
};

test("pdf row: running actions win over the stored state", () => {
  const generating = pdfRowView(converted, { generating: true, retrying: false });
  assert.equal(generating.kind, "converting");
  assert.equal(generating.text, "Converting to PDF…");
  assert.equal(generating.showDownload || generating.showRetry, false);
  const retrying = pdfRowView(failed, { generating: false, retrying: true });
  assert.equal(retrying.kind, "retrying");
  assert.equal(retrying.text, "Retrying PDF conversion…");
  // Converting shows even before the first generation finished.
  assert.equal(pdfRowView(null, { generating: true, retrying: false }).kind, "converting");
  assert.equal(pdfRowView(null, idle).kind, "none");
});

test("pdf row: converted shows the file and Download PDF", () => {
  const view = pdfRowView(converted, idle);
  assert.equal(view.text, "PDF ready");
  assert.equal(view.filename, "minutes-1a2b.pdf");
  assert.equal(view.showDownload, true);
  assert.equal(view.showRetry, false);
  assert.equal(view.warn, false);
});

test("pdf row: failed is amber with the reason and Retry PDF", () => {
  const view = pdfRowView(failed, idle);
  assert.equal(view.text, "PDF not available");
  assert.equal(view.detail, failed.pdf_error);
  assert.equal(view.warn, true);
  assert.equal(view.showRetry, true);
  assert.equal(view.showDownload, false);
  assert.equal(view.earlierPdf, false);
});

test("pdf row: failed with an earlier PDF keeps Download PDF", () => {
  const view = pdfRowView({ ...failed, has_pdf: true }, idle);
  assert.equal(view.showRetry, true);
  assert.equal(view.showDownload, true);
  assert.equal(view.earlierPdf, true);
  assert.equal(EARLIER_PDF_NOTE, "An earlier PDF of this document is available.");
});

test("pdf row: pending (not generating) offers Retry PDF", () => {
  const view = pdfRowView({ pdf_status: "pending", pdf_error: null, has_pdf: false }, idle);
  assert.equal(view.kind, "pending");
  assert.equal(view.text, "PDF conversion did not finish.");
  assert.equal(view.showRetry, true);
  assert.equal(view.showDownload, false);
  assert.equal(view.warn, true);
});

test("success message after Generate follows the PDF outcome", () => {
  assert.equal(generateSuccessMessage("converted"), "Document generated. DOCX and PDF are ready.");
  assert.equal(generateSuccessMessage("failed"), "Document generated. DOCX is ready; PDF failed (see below).");
  assert.match(generateSuccessMessage("pending"), /^Document generated\. DOCX is ready;/);
});

test("dashboard quick download prefers a converted PDF", () => {
  assert.equal(quickDownloadFormat({ pdf_status: "converted" }), "pdf");
  assert.equal(quickDownloadFormat({ pdf_status: "failed" }), "docx");
  assert.equal(quickDownloadFormat({ pdf_status: "pending" }), "docx");
  assert.equal(quickDownloadFormat(null), "docx");
});

test("markPdfFailed after a 503 retry and after a 410 download", () => {
  const info = { ...converted, pdf_attempts: 1, pdf_url: "/api/v1/documents/1/download/pdf" };
  const retried = markPdfFailed(info, "PDF service is busy", { attempted: true });
  assert.equal(retried.pdf_status, "failed");
  assert.equal(retried.pdf_error, "PDF service is busy");
  assert.equal(retried.pdf_attempts, 2);
  assert.equal(retried.has_pdf, true); // the earlier PDF is still there
  const missing = markPdfFailed(info, PDF_FILE_MISSING_MESSAGE, { fileMissing: true });
  assert.equal(missing.has_pdf, false);
  assert.equal(missing.pdf_url, null);
  assert.equal(missing.pdf_attempts, 1);
  assert.equal(pdfRowView(missing, idle).detail, "The PDF file is missing on the server. Click Retry PDF.");
});

function fakeTimers() {
  const pending = new Map<number, { callback: () => void; ms: number }>();
  let next = 1;
  return {
    pending,
    set: (callback: () => void, ms: number) => {
      const id = next++;
      pending.set(id, { callback, ms });
      return id;
    },
    clear: (handle: unknown) => {
      pending.delete(handle as number);
    },
    fireAll() {
      for (const [id, { callback }] of [...pending]) {
        pending.delete(id);
        callback();
      }
    },
  };
}

test("slow hint fires once after 8 s", () => {
  const timers = fakeTimers();
  let slow = 0;
  startSlowHintTimer(() => slow++, SLOW_PDF_HINT_MS, timers);
  assert.equal([...timers.pending.values()][0].ms, 8000);
  assert.equal(slow, 0);
  timers.fireAll();
  assert.equal(slow, 1);
  assert.equal(SLOW_PDF_HINT, "Converting to PDF can take up to a minute on first use.");
});

test("slow hint is cancelled when generation finishes or the panel unmounts", () => {
  const timers = fakeTimers();
  let slow = 0;
  const cancel = startSlowHintTimer(() => slow++, SLOW_PDF_HINT_MS, timers);
  cancel();
  assert.equal(timers.pending.size, 0);
  timers.fireAll();
  assert.equal(slow, 0);
  cancel(); // idempotent
});

test("slow hint with real timers", async () => {
  let slow = false;
  const cancel = startSlowHintTimer(() => (slow = true), 5);
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(slow, true);
  cancel(); // after firing: no-op
  let never = false;
  startSlowHintTimer(() => (never = true), 5)();
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(never, false);
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
