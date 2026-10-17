// Run with `npm test`. Pure helpers behind the V1.7 read-only preview page.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  completenessLabel,
  completenessPercent,
  editLinkForField,
  fieldDisplay,
  fieldNameFromHash,
  isComplete,
  missingFieldLinks,
  pdfPreviewKey,
  previewPdfState,
  previewTitle,
} from "../src/features/document-preview/preview-model.ts";
import {
  DOCX_MISSING_PREVIEW_MESSAGE,
  generationSummary,
  NOT_GENERATED_DETAIL,
  STALE_PREVIEW_DETAIL,
  STALE_PREVIEW_TITLE,
  UP_TO_DATE_TITLE,
} from "../src/features/documents/generation.ts";
import { documentKeys, keyStartsWith } from "../src/lib/query/keys.ts";
import type { DocumentPreview, PreviewField, PreviewGeneration } from "../src/lib/api/types.ts";

/** A realistic GET /documents/12/preview response (V1.7-P1.md section 3). */
const fixture: DocumentPreview = {
  document: {
    id: 12,
    name: "Academic Committee MoM",
    status: "draft",
    created_at: "2026-10-15T09:00:00",
    updated_at: "2026-10-15T10:12:00",
  },
  template: { id: 7, name: "T3-Format_MoM_updated", category: "mom", version: 1, has_processed_file: true },
  completeness: { required_total: 13, required_filled: 11, missing_required: ["verified_by", "approved_by"] },
  sections: [
    {
      name: "Meeting Details",
      fields: [
        {
          field_name: "meeting_date",
          label: "Meeting Date",
          field_type: "date",
          is_required: true,
          ai_enabled: false,
          display_order: 3,
          value: "2026-10-14",
          display_value: "14-10-2026",
          items: null,
          is_empty: false,
          missing_required: false,
        },
        {
          field_name: "venue",
          label: "Venue",
          field_type: "text",
          is_required: false,
          ai_enabled: false,
          display_order: 4,
          value: "Seminar Hall 2",
          display_value: "Seminar Hall 2",
          items: null,
          is_empty: false,
          missing_required: false,
        },
      ],
    },
    {
      name: "Discussion",
      fields: [
        {
          field_name: "agenda_points",
          label: "Agenda Points",
          field_type: "list",
          is_required: true,
          ai_enabled: true,
          display_order: 5,
          value: '["Review of syllabus","Exam schedule"]',
          display_value: "Review of syllabus\nExam schedule",
          items: ["Review of syllabus", "Exam schedule"],
          is_empty: false,
          missing_required: false,
        },
        {
          field_name: "summary",
          label: "Summary",
          field_type: "textarea",
          is_required: false,
          ai_enabled: true,
          display_order: 6,
          value: "The committee met.",
          display_value: "The committee met.",
          items: null,
          is_empty: false,
          missing_required: false,
        },
      ],
    },
    {
      name: "Sign-off",
      fields: [
        {
          field_name: "verified_by",
          label: "Verified by",
          field_type: "text",
          is_required: true,
          ai_enabled: false,
          display_order: 12,
          value: null,
          display_value: "",
          items: null,
          is_empty: true,
          missing_required: true,
        },
        {
          field_name: "approved_by",
          label: "Approved by",
          field_type: "text",
          is_required: true,
          ai_enabled: false,
          display_order: 13,
          value: "",
          display_value: "",
          items: null,
          is_empty: true,
          missing_required: true,
        },
      ],
    },
  ],
  generation: {
    generated_at: "2026-10-15T10:15:00",
    is_stale: false,
    template_version: 1,
    docx_available: true,
    docx_url: "/api/v1/documents/12/download?format=docx",
    pdf_status: "converted",
    pdf_error: null,
    pdf_available: true,
    pdf_url: "/api/v1/documents/12/download/pdf",
    pdf_filename: "academic-committee-mom.pdf",
  },
  permissions: { can_edit: true, can_generate: true, can_download: true },
};

const field = (name: string): PreviewField => {
  for (const section of fixture.sections) {
    const found = section.fields.find((f) => f.field_name === name);
    if (found) return found;
  }
  throw new Error(`no field ${name}`);
};

// --- completeness ---

test("completeness: partial", () => {
  assert.equal(completenessPercent(fixture.completeness), 84);
  assert.equal(completenessLabel(fixture.completeness), "11 of 13 required fields filled");
  assert.equal(isComplete(fixture.completeness), false);
});

test("completeness: all filled", () => {
  const c = { required_total: 13, required_filled: 13, missing_required: [] };
  assert.equal(completenessPercent(c), 100);
  assert.equal(completenessLabel(c), "All required fields filled");
  assert.equal(isComplete(c), true);
});

test("completeness: no required fields counts as complete", () => {
  const c = { required_total: 0, required_filled: 0, missing_required: [] };
  assert.equal(completenessPercent(c), 100);
  assert.equal(completenessLabel(c), "All required fields filled");
});

test("completeness: nothing filled, and never 100% before complete", () => {
  assert.equal(completenessPercent({ required_total: 4, required_filled: 0, missing_required: ["a", "b", "c", "d"] }), 0);
  assert.equal(completenessPercent({ required_total: 200, required_filled: 199, missing_required: ["x"] }), 99);
  assert.equal(completenessPercent({ required_total: 2, required_filled: 5, missing_required: [] }), 100);
});

test("missing field links use labels and deep-link to the edit page", () => {
  assert.deepEqual(missingFieldLinks(fixture), [
    { fieldName: "verified_by", label: "Verified by", href: "/documents/12/edit#field-verified_by" },
    { fieldName: "approved_by", label: "Approved by", href: "/documents/12/edit#field-approved_by" },
  ]);
  const unknown = { ...fixture, completeness: { ...fixture.completeness, missing_required: ["ghost_field"] } };
  assert.equal(missingFieldLinks(unknown)[0].label, "ghost_field");
});

// --- field display ---

test("field display: text uses display_value unchanged (no browser date formatting)", () => {
  assert.deepEqual(fieldDisplay(field("meeting_date")), { kind: "text", text: "14-10-2026" });
  assert.deepEqual(fieldDisplay(field("venue")), { kind: "text", text: "Seminar Hall 2" });
});

test("field display: list uses items", () => {
  assert.deepEqual(fieldDisplay(field("agenda_points")), {
    kind: "list",
    items: ["Review of syllabus", "Exam schedule"],
  });
  const blankList = { ...field("agenda_points"), items: ["", "  "] };
  assert.deepEqual(fieldDisplay(blankList), { kind: "empty" });
  const nullItems = { ...field("agenda_points"), items: null };
  assert.deepEqual(fieldDisplay(nullItems), { kind: "empty" });
});

test("field display: multiline for textarea or text containing a newline", () => {
  assert.deepEqual(fieldDisplay(field("summary")), { kind: "multiline", text: "The committee met." });
  const twoLines = { ...field("venue"), display_value: "Block A\nRoom 4" };
  assert.deepEqual(fieldDisplay(twoLines), { kind: "multiline", text: "Block A\nRoom 4" });
});

test("field display: empty", () => {
  assert.deepEqual(fieldDisplay(field("verified_by")), { kind: "empty" });
  // is_empty wins even if a stray value is present.
  assert.deepEqual(fieldDisplay({ ...field("venue"), is_empty: true }), { kind: "empty" });
  assert.deepEqual(fieldDisplay({ ...field("venue"), display_value: "   " }), { kind: "empty" });
});

// --- links and hashes ---

test("edit link for a field", () => {
  assert.equal(editLinkForField(12, "meeting_date"), "/documents/12/edit#field-meeting_date");
  assert.equal(editLinkForField(3, "a b"), "/documents/3/edit#field-a%20b");
});

test("field name from a location hash", () => {
  assert.equal(fieldNameFromHash("#field-meeting_date"), "meeting_date");
  assert.equal(fieldNameFromHash("#field-a%20b"), "a b");
  assert.equal(fieldNameFromHash("#field-"), null);
  assert.equal(fieldNameFromHash("#section-x"), null);
  assert.equal(fieldNameFromHash(""), null);
  assert.equal(fieldNameFromHash(undefined), null);
  assert.equal(fieldNameFromHash("#field-%E0%A4"), "%E0%A4");
});

test("round trip: link hash back to the field name", () => {
  const link = editLinkForField(12, "verified_by");
  assert.equal(fieldNameFromHash(link.slice(link.indexOf("#"))), "verified_by");
});

// --- header ---

test("preview title falls back to Untitled draft", () => {
  assert.equal(previewTitle("Academic Committee MoM"), "Academic Committee MoM");
  assert.equal(previewTitle(null), "Untitled draft");
  assert.equal(previewTitle("   "), "Untitled draft");
});

// --- generation summary ---

const gen = fixture.generation as PreviewGeneration;

test("generation summary: never generated", () => {
  assert.deepEqual(generationSummary(null, false), {
    tone: "muted",
    title: "Not generated yet",
    detail: NOT_GENERATED_DETAIL,
  });
});

test("generation summary: fresh", () => {
  assert.deepEqual(generationSummary(gen, false), { tone: "ok", title: UP_TO_DATE_TITLE, detail: "PDF ready" });
  assert.equal(generationSummary({ ...gen, pdf_status: "failed" }, false).detail, "PDF not available");
});

test("generation summary: stale", () => {
  assert.deepEqual(generationSummary({ ...gen, is_stale: true }, true), {
    tone: "warn",
    title: STALE_PREVIEW_TITLE,
    detail: STALE_PREVIEW_DETAIL,
  });
  assert.equal(STALE_PREVIEW_TITLE, "Values changed since the last generation");
});

test("generation summary: DOCX missing on the server wins over stale", () => {
  const summary = generationSummary({ ...gen, docx_available: false }, true);
  assert.equal(summary.tone, "warn");
  assert.equal(summary.detail, DOCX_MISSING_PREVIEW_MESSAGE);
  assert.equal(DOCX_MISSING_PREVIEW_MESSAGE, "The generated file is missing on the server. Regenerate to recreate it.");
});

// --- PDF state for the shared PDF row and the inline preview ---

test("preview PDF state maps pdf_available to has_pdf", () => {
  assert.equal(previewPdfState(null), null);
  assert.deepEqual(previewPdfState(gen), {
    pdf_status: "converted",
    pdf_error: null,
    pdf_filename: "academic-committee-mom.pdf",
    has_pdf: true,
  });
  const failed = previewPdfState({ ...gen, pdf_status: "failed", pdf_error: "LibreOffice timed out", pdf_available: false });
  assert.equal(failed?.has_pdf, false);
  assert.equal(failed?.pdf_error, "LibreOffice timed out");
});

test("PDF preview key changes with generated_at and is null without a PDF", () => {
  const key = pdfPreviewKey(12, gen);
  assert.ok(key);
  assert.notEqual(pdfPreviewKey(12, { ...gen, generated_at: "2026-10-15T11:00:00" }), key);
  assert.equal(pdfPreviewKey(12, { ...gen, pdf_available: false }), null);
  assert.equal(pdfPreviewKey(12, null), null);
});

// --- cache invalidation ---

test("preview query key sits under the draft detail (invalidated by save / generate / retry PDF)", () => {
  assert.deepEqual(documentKeys.preview(12), ["documents", "detail", 12, "preview"]);
  assert.ok(keyStartsWith(documentKeys.preview(12), documentKeys.detail(12)));
  assert.ok(keyStartsWith(documentKeys.preview(12), documentKeys.all));
  assert.ok(!keyStartsWith(documentKeys.preview(12), documentKeys.detail(13)));
});
