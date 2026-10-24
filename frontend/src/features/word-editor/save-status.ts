/**
 * Pure helpers for the Word editor's save state (V1.7 P2.1). ONLYOFFICE saves
 * about 10 s after the editor closes, so the page polls the session until a
 * final state. Type imports only (unit tested with `node --test`).
 */
import type { EditorSessionRead, EditorSessionStatus, EditorTarget } from "../../lib/api/types";

/** Stop polling after this long and tell the user the save continues without them. */
export const SAVE_POLL_TIMEOUT_MS = 90_000;
export const STILL_SAVING_MESSAGE =
  "Still saving. You can leave this page; the new revision/version will appear when it is done.";

const FINAL_STATUSES: readonly EditorSessionStatus[] = ["saved", "failed", "closed", "expired"];

export function isFinal(status: EditorSessionStatus): boolean {
  return FINAL_STATUSES.includes(status);
}

/** 1 s for the first five polls, then 2 s. */
export function nextPollDelay(attempt: number): number {
  return attempt < 5 ? 1000 : 2000;
}

/** The status line after "Done editing". */
export function sessionMessage(
  session: Pick<EditorSessionRead, "status" | "result_revision" | "result_version" | "error">,
  target: EditorTarget,
): string {
  switch (session.status) {
    case "open":
    case "saving":
      return "Saving your changes…";
    case "saved":
      if (target === "template") {
        return session.result_revision ? `Saved as revision ${session.result_revision}.` : "Saved.";
      }
      return session.result_version ? `Version ${session.result_version} saved (edited manually).` : "Saved.";
    case "closed":
      return "No changes were made.";
    case "expired":
      return "The editing session expired before it was saved. Open the editor again.";
    case "failed":
      return session.error ? `Saving failed: ${session.error}` : "Saving failed. Open the editor again.";
  }
}

/** A user-facing message for a failed "open the editor" (by HTTP status). */
export function openErrorMessage(status: number | undefined, fallback?: string): string {
  if (status === 503) return "The document editor is not available.";
  if (status === 410) return fallback || "This version's files were removed.";
  if (status === 409) return fallback || "This file cannot be edited right now.";
  if (status === 403) return fallback || "You cannot edit this file.";
  if (status === 404) return fallback || "This file does not exist.";
  return fallback || "The document editor could not be opened. Please try again.";
}
