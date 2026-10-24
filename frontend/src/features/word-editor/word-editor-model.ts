/**
 * Pure rules for the Word file editor (V1.7 P2.1) used by always-loaded
 * pages: which entry points show and the "manual edits" generate conflict.
 * Labels for the lazy editor / review pages live in editor-review-model.ts.
 * Type imports only (`node --test`).
 */
import type { TemplateResponse } from "../../lib/api/types";

// Same rule as the backend (document_permissions.EDITABLE_STATUSES).
export const EDITABLE_DOCUMENT_STATUSES = ["draft", "generated"];

export const MANAGER_EDIT_WARNING =
  "Everyone using this template will get your changes in documents they generate from now on. Continue?";
export const VALUES_UNCHANGED_NOTE = "The form values were not changed by manual edits.";

type TemplateAccess = Pick<TemplateResponse, "can_manage" | "is_personal_copy" | "visibility">;

export interface TemplateEditorActions {
  /** "Customize for me": anyone who can see the template (copies of copies are fine). */
  customize: boolean;
  /** "Edit Word file": managers of the template (a personal copy is managed by its owner). */
  editFile: boolean;
  /** Ask before editing a shared original. */
  confirmEdit: boolean;
}

export function templateEditorActions(
  template: TemplateAccess & { original_file_path?: string | null },
  editorEnabled: boolean,
): TemplateEditorActions {
  if (!editorEnabled || !template.original_file_path) {
    return { customize: false, editFile: false, confirmEdit: false };
  }
  const editFile = template.can_manage;
  return {
    customize: !template.is_personal_copy || !template.can_manage,
    editFile,
    confirmEdit: editFile && !template.is_personal_copy && template.visibility !== "private",
  };
}

/** "Edit Word file" on a generated document / version. */
export function canEditDocumentFile(
  options: { editorEnabled: boolean; documentStatus: string | null | undefined; hasDocx: boolean },
): boolean {
  return (
    options.editorEnabled &&
    options.hasDocx &&
    EDITABLE_DOCUMENT_STATUSES.includes(options.documentStatus ?? "")
  );
}

/** The editor page URL for a document (default: its latest version). */
export function documentEditorPath(documentId: number, version?: number | null): string {
  return version ? `/documents/${documentId}/edit-file?version=${version}` : `/documents/${documentId}/edit-file`;
}

export function copyBadgeText(template: Pick<TemplateResponse, "is_personal_copy" | "parent_template_name">): string | null {
  if (!template.is_personal_copy) return null;
  return template.parent_template_name ? `My copy of ${template.parent_template_name}` : "My copy";
}

export interface ManualEditsConflict {
  message: string;
  version: number | null;
}

/** The 409 {code: "manual_edits"} from generate, or null for any other error. */
export function manualEditsConflict(error: unknown): ManualEditsConflict | null {
  if (!error || typeof error !== "object") return null;
  const { status, detail, message } = error as { status?: number; detail?: unknown; message?: string };
  if (status !== 409 || !detail || typeof detail !== "object") return null;
  const coded = detail as { code?: unknown; version?: unknown; detail?: unknown };
  if (coded.code !== "manual_edits") return null;
  return {
    message: typeof coded.detail === "string" ? coded.detail : message || "The latest version was edited manually.",
    version: typeof coded.version === "number" ? coded.version : null,
  };
}
