/**
 * Pure helpers for the V1.7 Phase 2 version history (panel, version page,
 * toasts). Type imports only, so they can be unit tested with `node --test`
 * (frontend/tests/versions.test.ts).
 */
import type { DocumentVersion } from "../../lib/api/types";

export type VersionFormat = "docx" | "pdf";

export const PRUNED_NOTE = "Files removed by retention";
export const PRUNED_DETAIL =
  "The files of this version were removed to save space. Its values are still shown here: restore them and generate again to get the files back.";
export const NO_PDF_NOTE = "No PDF for this version";
export const FILE_MISSING_NOTE = "File missing on the server";
export const NOT_EDITABLE_RESTORE = "This document can no longer be edited, so a version cannot be restored.";

/** "v3" */
export function versionLabel(version: Pick<DocumentVersion, "version">): string {
  return `v${version.version}`;
}

/** "v3 · 2 hours ago · by Priya" (relativeTime from the caller, e.g. date-fns). */
export function versionMeta(version: Pick<DocumentVersion, "version" | "created_by_name">, relativeTime: string): string {
  return [versionLabel(version), relativeTime, `by ${version.created_by_name}`].filter(Boolean).join(" · ");
}

/**
 * "Changed: Discussion, Venue" from field names (labels where known).
 * Version 1 is the first version; an unchanged regenerate says so.
 */
export function changedFieldsText(
  version: Pick<DocumentVersion, "version" | "changed_fields">,
  labelOf: (fieldName: string) => string = (name) => name,
): string {
  if (version.version <= 1) return "First version";
  if (version.changed_fields.length === 0) return "No value changes";
  return `Changed: ${version.changed_fields.map(labelOf).join(", ")}`;
}

/** Short PDF state of a version. */
export function versionPdfLabel(version: Pick<DocumentVersion, "pdf_status" | "has_pdf" | "files_pruned">): string {
  if (version.files_pruned) return "Files removed";
  if (version.has_pdf) return "PDF ready";
  if (version.pdf_status === "failed") return "PDF failed";
  if (version.pdf_status === "pending") return "PDF pending";
  return "No PDF";
}

export interface VersionDownloadState {
  enabled: boolean;
  /** Why the button is disabled (tooltip / helper text). */
  reason: string | null;
}

/** Whether a version's DOCX / PDF can be downloaded, and why not. */
export function versionDownloadState(
  version: Pick<DocumentVersion, "files_pruned" | "has_docx" | "has_pdf" | "pdf_status">,
  format: VersionFormat,
): VersionDownloadState {
  if (version.files_pruned) return { enabled: false, reason: PRUNED_NOTE };
  if (format === "docx") return version.has_docx ? { enabled: true, reason: null } : { enabled: false, reason: FILE_MISSING_NOTE };
  if (version.has_pdf) return { enabled: true, reason: null };
  return { enabled: false, reason: version.pdf_status === "converted" ? FILE_MISSING_NOTE : NO_PDF_NOTE };
}

/** The confirm text before restoring. */
export function restoreConfirmText(version: Pick<DocumentVersion, "version">): string {
  return `Replace the current values with ${versionLabel(version)}? Unsaved changes will be lost.`;
}

/** A user-facing message for a failed version download (by HTTP status). */
export function versionDownloadErrorMessage(status: number | undefined, format: VersionFormat, fallback?: string): string {
  if (status === 410) {
    return "This file is no longer on the server (removed to save space, or missing). The version's values are still available.";
  }
  if (status === 409) return format === "pdf" ? `${NO_PDF_NOTE}.` : "This file is not available.";
  if (status === 404) return "This version no longer exists.";
  return fallback || "Download failed. Please try again.";
}

/** A user-facing message for a failed restore. */
export function restoreErrorMessage(status: number | undefined, fallback?: string): string {
  if (status === 409) return NOT_EDITABLE_RESTORE;
  if (status === 404) return "This version no longer exists.";
  return fallback || "Restore failed. Please try again.";
}
