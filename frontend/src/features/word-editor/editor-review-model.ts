/**
 * Labels for the lazy Word editor pages (V1.7 P2.1): template revisions,
 * the field-changes summary and field chips. Type imports only (`node --test`).
 */
import type { FieldChanges, RevisionSource, TemplateRevision } from "../../lib/api/types";

const REVISION_SOURCE_LABELS: Record<RevisionSource, string> = {
  upload: "Uploaded",
  clean: "Cleaned",
  fix_placeholders: "Placeholders fixed",
  customize: "Copied",
  manual_edit: "Edited in Word",
  restore: "Restored",
};

export function revisionSourceLabel(source: RevisionSource | string): string {
  return REVISION_SOURCE_LABELS[source as RevisionSource] ?? source;
}

/** "+2 fields · −1 field · 3 blanks" (empty when nothing changed). */
export function revisionChangeText(
  revision: Pick<TemplateRevision, "placeholders_added" | "placeholders_removed" | "blank_suggestions">,
): string {
  const parts: string[] = [];
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  if (revision.placeholders_added.length) parts.push(`+${plural(revision.placeholders_added.length, "field")}`);
  if (revision.placeholders_removed.length) parts.push(`−${plural(revision.placeholders_removed.length, "field")}`);
  if (revision.blank_suggestions) parts.push(plural(revision.blank_suggestions, "blank"));
  return parts.join(" · ");
}

export function restoreRevisionConfirmText(revision: Pick<TemplateRevision, "revision">): string {
  return `Make revision ${revision.revision} the current file? It is saved as a new revision; nothing is deleted.`;
}

export type FieldChangesKind = "render_error" | "none" | "changes";

export interface FieldChangesSummary {
  kind: FieldChangesKind;
  title: string;
  lines: string[];
  /** Where to go next in the existing pipeline: clean (blanks), detect ({{ }}), fields. */
  cleanFirst: boolean;
  detectNew: boolean;
  reviewFields: boolean;
}

export function fieldChangesSummary(changes: FieldChanges): FieldChangesSummary {
  if (!changes.renderable) {
    return {
      kind: "render_error",
      title: "The edited file cannot be used yet",
      lines: [changes.render_error || "The file has a broken placeholder."],
      cleanFirst: false,
      detectNew: false,
      reviewFields: false,
    };
  }
  const lines: string[] = [];
  const plural = (n: number, one: string, many: string) => (n === 1 ? one : many.replace("#", String(n)));
  if (changes.added.length) lines.push(plural(changes.added.length, "1 new field", "# new fields"));
  if (changes.removed.length) {
    lines.push(plural(changes.removed.length, "1 field is no longer in the file", "# fields are no longer in the file"));
  }
  if (changes.blank_suggestions) {
    lines.push(plural(changes.blank_suggestions, "1 blank can become a field", "# blanks can become fields"));
  }
  if (!changes.has_changes && changes.blank_suggestions === 0) {
    return { kind: "none", title: "No field changes. Template updated.", lines: [], cleanFirst: false, detectNew: false, reviewFields: false };
  }
  return {
    kind: "changes",
    title: "Review the changes to the form",
    lines,
    cleanFirst: changes.blank_suggestions > 0,
    detectNew: changes.added.length > 0,
    reviewFields: changes.added.length > 0 || changes.removed.length > 0,
  };
}

/** "{{ date_of_meeting }}" for a field chip. */
export function placeholderText(fieldName: string): string {
  return `{{ ${fieldName} }}`;
}
