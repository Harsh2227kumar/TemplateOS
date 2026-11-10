/**
 * Pure helpers for download history (V1.7 Phase 3). Type imports only, so
 * they run under `node --test` (frontend/tests/history-model.test.ts).
 */
import type { DownloadHistoryItem } from "../../lib/api/types";

export type DownloadFormat = "docx" | "pdf";

/** "1.2 MB", "820 KB", "512 B"; "" when unknown. */
export function humanFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : Math.round(value * 10) / 10} ${units[unit]}`;
}

/** "v2 · PDF · Edited manually" */
export function downloadLabel(item: Pick<DownloadHistoryItem, "version" | "format" | "version_source">): string {
  return [
    item.version ? `v${item.version}` : null,
    item.format.toUpperCase(),
    item.version_source === "manual_edit" ? "Edited manually" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** The document's name, marked when it was deleted (the name is a snapshot). */
export function downloadDocumentName(item: Pick<DownloadHistoryItem, "document_name" | "document_exists">): string {
  return item.document_exists ? item.document_name : `${item.document_name} (deleted)`;
}

/** API path of a download (the latest version when `version` is omitted). */
export function downloadPath(documentId: number, format: DownloadFormat, version?: number | null): string {
  if (version) return `/documents/${documentId}/versions/${version}/download/${format}`;
  return format === "pdf" ? `/documents/${documentId}/download/pdf` : `/documents/${documentId}/download?format=docx`;
}

/** A user-facing message for a failed download (by HTTP status). */
export function downloadErrorMessage(status: number | undefined, fallback?: string): string {
  if (status === 403) return "You don't have access to this file.";
  if (status === 404) return "Not found.";
  if (status === 409) return "The PDF is not available yet.";
  if (status === 410) return "This file was removed by retention or is missing. Regenerate to recreate it.";
  return fallback || "Download failed. Please try again.";
}
