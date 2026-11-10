/**
 * Pure helpers for V1.6 document generation (labels, PDF row state,
 * filenames, the slow-conversion hint timer).
 * Kept free of runtime imports so they can be unit tested with `node --test`.
 */

/** Mirrors the backend: generated_files.pdf_status. */
export type PdfStatus = "pending" | "converted" | "failed";
export type DownloadFormat = "docx" | "pdf";

/** Short label for the PDF state of a generated document. */
export function pdfStatusLabel(status: PdfStatus | null | undefined): string {
  switch (status) {
    case "converted":
      return "PDF ready";
    case "failed":
      return "PDF not available";
    case "pending":
      return "PDF conversion did not finish.";
    default:
      return "Not generated yet";
  }
}

/** The PDF fields of a generated document that the PDF row needs. */
export interface PdfState {
  pdf_status: PdfStatus;
  pdf_error: string | null;
  pdf_filename?: string | null;
  has_pdf?: boolean;
}

export type PdfRowKind = "converting" | "retrying" | "converted" | "failed" | "pending" | "none";

export interface PdfRowView {
  kind: PdfRowKind;
  /** Status text (announced through aria-live). */
  text: string;
  /** The failure reason (failed only). */
  detail: string | null;
  /** File name shown next to "PDF ready". */
  filename: string | null;
  showDownload: boolean;
  showRetry: boolean;
  /** Failed, but an earlier PDF of this document can still be downloaded. */
  earlierPdf: boolean;
  /** Amber notice (failed / pending). PDF problems are never red. */
  warn: boolean;
}

export const EARLIER_PDF_NOTE = "An earlier PDF of this document is available.";

/** What the PDF row of the generation panel shows. Running actions win. */
export function pdfRowView(
  pdf: PdfState | null | undefined,
  { generating, retrying }: { generating: boolean; retrying: boolean },
): PdfRowView {
  const base: PdfRowView = {
    kind: "none",
    text: "",
    detail: null,
    filename: null,
    showDownload: false,
    showRetry: false,
    earlierPdf: false,
    warn: false,
  };
  if (generating) return { ...base, kind: "converting", text: "Converting to PDF…" };
  if (retrying) return { ...base, kind: "retrying", text: "Retrying PDF conversion…" };
  if (!pdf) return base;
  const hasPdf = Boolean(pdf.has_pdf);
  switch (pdf.pdf_status) {
    case "converted":
      return {
        ...base,
        kind: "converted",
        text: pdfStatusLabel("converted"),
        filename: pdf.pdf_filename ?? null,
        showDownload: true,
      };
    case "failed":
      return {
        ...base,
        kind: "failed",
        text: pdfStatusLabel("failed"),
        detail: pdf.pdf_error || null,
        showRetry: true,
        showDownload: hasPdf,
        earlierPdf: hasPdf,
        warn: true,
      };
    default:
      return {
        ...base,
        kind: "pending",
        text: pdfStatusLabel("pending"),
        showRetry: true,
        showDownload: hasPdf,
        warn: true,
      };
  }
}

/** Success message after Generate, by the PDF outcome. */
export function generateSuccessMessage(status: PdfStatus): string {
  switch (status) {
    case "converted":
      return "Document generated. DOCX and PDF are ready.";
    case "failed":
      return "Document generated. DOCX is ready; PDF failed (see below).";
    default:
      return "Document generated. DOCX is ready; PDF conversion did not finish (see below).";
  }
}

/** Dashboard quick download: the PDF when it is converted, else the DOCX. */
export function quickDownloadFormat(pdf: Pick<PdfState, "pdf_status"> | null | undefined): DownloadFormat {
  return pdf?.pdf_status === "converted" ? "pdf" : "docx";
}

export const RETRY_DOCX_MISSING_MESSAGE = "The generated DOCX is missing on the server. Click Regenerate.";
export const PDF_FILE_MISSING_MESSAGE = "The PDF file is missing on the server. Click Retry PDF.";

/** The local PDF state after a failed retry / download (the server already recorded it). */
export function markPdfFailed<T extends PdfState & { pdf_attempts?: number; pdf_url?: string | null }>(
  current: T,
  reason: string,
  { fileMissing = false, attempted = false }: { fileMissing?: boolean; attempted?: boolean } = {},
): T {
  return {
    ...current,
    pdf_status: "failed",
    pdf_error: reason,
    ...(fileMissing ? { has_pdf: false, pdf_url: null, pdf_filename: null } : {}),
    ...(attempted && typeof current.pdf_attempts === "number" ? { pdf_attempts: current.pdf_attempts + 1 } : {}),
  } as T;
}

export const SLOW_PDF_HINT_MS = 8000;
export const SLOW_PDF_HINT = "Converting to PDF can take up to a minute on first use.";

/**
 * Call onSlow once `delayMs` after starting, unless the returned cancel
 * function runs first (generation finished or the component unmounted).
 */
export function startSlowHintTimer(
  onSlow: () => void,
  delayMs: number = SLOW_PDF_HINT_MS,
  timers: {
    set: (callback: () => void, ms: number) => unknown;
    clear: (handle: unknown) => void;
  } = {
    set: (callback, ms) => setTimeout(callback, ms),
    clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  },
): () => void {
  let done = false;
  const handle = timers.set(() => {
    if (done) return;
    done = true;
    onSlow();
  }, delayMs);
  return () => {
    if (done) return;
    done = true;
    timers.clear(handle);
  };
}

/** Mirrors the backend's filename rule, used when the header is unreadable. */
export function fallbackDownloadFilename(
  name: string | null | undefined,
  documentId: number,
  format: DownloadFormat,
): string {
  const stem = (name ?? "")
    .replace(/[^\p{L}\p{N}\s().,_-]+/gu, " ")
    .replace(/\s+/g, " ")
    .replace(/^[\s.\-_]+|[\s.\-_]+$/g, "")
    .slice(0, 100)
    .trim();
  return `${stem || `document-${documentId}`}.${format}`;
}

/**
 * Filename from a Content-Disposition header. Prefers the RFC 5987
 * `filename*=UTF-8''...` form, then a quoted or bare `filename=`.
 */
export function filenameFromContentDisposition(header: string | null | undefined): string | null {
  if (!header) return null;
  const extended = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(header);
  if (extended) {
    try {
      const decoded = decodeURIComponent(extended[2].trim().replace(/^"|"$/g, ""));
      if (decoded) return sanitizeFilename(decoded);
    } catch {
      // Malformed encoding: fall through to the plain filename.
    }
  }
  const quoted = /filename\s*=\s*"((?:[^"\\]|\\.)*)"/i.exec(header);
  if (quoted && quoted[1]) return sanitizeFilename(quoted[1].replace(/\\(.)/g, "$1"));
  const bare = /filename\s*=\s*([^;\s]+)/i.exec(header);
  if (bare && bare[1]) return sanitizeFilename(bare[1]);
  return null;
}

/** Strip path separators so a header can never point outside Downloads. */
function sanitizeFilename(name: string): string {
  return name.replace(/[/\\]/g, "_").trim();
}

// --- V1.7 preview page: one-line summary of the generated files ---

export const NOT_GENERATED_DETAIL = "Generate the document to create the Word file and its PDF.";
export const DOCX_MISSING_PREVIEW_MESSAGE = "The generated file is missing on the server. Regenerate to recreate it.";
export const STALE_PREVIEW_TITLE = "Values changed since the last generation";
export const STALE_PREVIEW_DETAIL = "Regenerate to include your latest values.";
export const UP_TO_DATE_TITLE = "Generated document is up to date";

export type GenerationTone = "ok" | "warn" | "muted";

export interface GenerationSummary {
  tone: GenerationTone;
  title: string;
  detail: string;
}

/**
 * What the preview page says about the generated files. Lives here (not in
 * the preview feature) so it reuses these labels without a runtime import.
 * A missing DOCX wins over "stale": regenerating fixes both.
 */
export function generationSummary(
  generation: { docx_available: boolean; pdf_status: PdfStatus } | null | undefined,
  isStale: boolean,
): GenerationSummary {
  if (!generation) return { tone: "muted", title: pdfStatusLabel(null), detail: NOT_GENERATED_DETAIL };
  if (!generation.docx_available) {
    return { tone: "warn", title: "Generated file missing", detail: DOCX_MISSING_PREVIEW_MESSAGE };
  }
  if (isStale) return { tone: "warn", title: STALE_PREVIEW_TITLE, detail: STALE_PREVIEW_DETAIL };
  return { tone: "ok", title: UP_TO_DATE_TITLE, detail: pdfStatusLabel(generation.pdf_status) };
}

/** "Generate document", or "Regenerate" once a generated copy exists. */
export function generateActionLabel(generated: boolean, stale: boolean): string {
  if (!generated) return "Generate document";
  return stale ? "Regenerate (values changed)" : "Regenerate";
}

/** "Version 3 created" after a generate (V1.7 P2; null without a version number). */
export function versionCreatedText(result: { version?: number | null }): string | null {
  return result.version ? `Version ${result.version} created` : null;
}
