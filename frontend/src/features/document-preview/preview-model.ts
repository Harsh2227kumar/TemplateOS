/**
 * Pure helpers for the V1.7 read-only preview page.
 * Kept free of runtime imports (type imports only) so they can be unit tested
 * with `node --test`. The generated-files summary (`generationSummary`) lives
 * in features/documents/generation.ts next to the labels it reuses.
 */
import type { PdfState } from "../documents/generation";
import type {
  DocumentPreview,
  PreviewCompleteness,
  PreviewField,
  PreviewGeneration,
} from "../../lib/api/types";

/** 0..100, rounded down so "almost done" never shows 100%. No required fields = 100. */
export function completenessPercent(c: PreviewCompleteness): number {
  if (c.required_total <= 0) return 100;
  const ratio = c.required_filled / c.required_total;
  return Math.max(0, Math.min(100, Math.floor(ratio * 100)));
}

export function isComplete(c: PreviewCompleteness): boolean {
  return c.required_total <= 0 || c.required_filled >= c.required_total;
}

/** "All required fields filled" or "11 of 13 required fields filled". */
export function completenessLabel(c: PreviewCompleteness): string {
  if (isComplete(c)) return "All required fields filled";
  return `${Math.max(0, c.required_filled)} of ${c.required_total} required fields filled`;
}

export type FieldDisplayKind = "text" | "multiline" | "list" | "empty";

export interface FieldDisplay {
  kind: FieldDisplayKind;
  /** text / multiline: the backend's display_value, unchanged. */
  text?: string;
  /** list: the backend's items, unchanged. */
  items?: string[];
}

/**
 * How one preview row renders. Never re-formats: text is `display_value`,
 * list items are `items`. Phase 2 (rich text) adds a kind here.
 */
export function fieldDisplay(field: PreviewField): FieldDisplay {
  if (field.is_empty) return { kind: "empty" };
  if (field.field_type === "list") {
    const items = (field.items ?? []).filter((item) => item.trim() !== "");
    return items.length > 0 ? { kind: "list", items } : { kind: "empty" };
  }
  const text = field.display_value ?? "";
  if (text.trim() === "") return { kind: "empty" };
  if (field.field_type === "textarea" || text.includes("\n")) return { kind: "multiline", text };
  return { kind: "text", text };
}

const FIELD_HASH_PREFIX = "#field-";

/** Edit page deep link that scrolls to and focuses one field. */
export function editLinkForField(documentId: number, fieldName: string): string {
  return `/documents/${documentId}/edit${FIELD_HASH_PREFIX}${encodeURIComponent(fieldName)}`;
}

/** The field name from a `#field-<name>` location hash; null for any other hash. */
export function fieldNameFromHash(hash: string | null | undefined): string | null {
  if (!hash || !hash.startsWith(FIELD_HASH_PREFIX)) return null;
  const raw = hash.slice(FIELD_HASH_PREFIX.length);
  if (!raw) return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export interface MissingFieldLink {
  fieldName: string;
  label: string;
  href: string;
}

/** Missing required fields as edit links, labelled from the sections (falls back to the name). */
export function missingFieldLinks(preview: Pick<DocumentPreview, "document" | "completeness" | "sections">): MissingFieldLink[] {
  const labels = new Map<string, string>();
  for (const section of preview.sections) {
    for (const field of section.fields) labels.set(field.field_name, field.label?.trim() || field.field_name);
  }
  return preview.completeness.missing_required.map((fieldName) => ({
    fieldName,
    label: labels.get(fieldName) ?? fieldName,
    href: editLinkForField(preview.document.id, fieldName),
  }));
}

/** The draft's display name. */
export function previewTitle(name: string | null | undefined): string {
  const trimmed = name?.trim();
  return trimmed ? trimmed : "Untitled draft";
}

/** The preview's generation in the shape the shared PDF row (pdfRowView) reads. */
export function previewPdfState(generation: PreviewGeneration | null | undefined): PdfState | null {
  if (!generation) return null;
  return {
    pdf_status: generation.pdf_status,
    pdf_error: generation.pdf_error,
    pdf_filename: generation.pdf_filename,
    has_pdf: generation.pdf_available,
  };
}

/** Identity of the generated PDF: the inline preview refetches (and revokes) when it changes. */
export function pdfPreviewKey(documentId: number, generation: PreviewGeneration | null | undefined): string | null {
  if (!generation || !generation.pdf_available) return null;
  return `${documentId}:${generation.generated_at}:${generation.pdf_filename ?? ""}`;
}
