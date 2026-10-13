/**
 * Pure helpers for V1.6 document generation (labels, filenames).
 * Kept free of runtime imports so they can be unit tested with `node --test`.
 */

export type PdfStatus = "ok" | "failed" | "not_configured";
export type DownloadFormat = "docx" | "pdf";

/** Short label for the PDF state of a generated document. */
export function pdfStatusLabel(status: PdfStatus | null | undefined): string {
  switch (status) {
    case "ok":
      return "PDF ready";
    case "failed":
      return "PDF conversion failed";
    case "not_configured":
      return "PDF conversion is not set up on the server";
    default:
      return "Not generated yet";
  }
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

/** "Generate document", or "Regenerate" once a generated copy exists. */
export function generateActionLabel(generated: boolean, stale: boolean): string {
  if (!generated) return "Generate document";
  return stale ? "Regenerate (values changed)" : "Regenerate";
}
