// Shared helpers for the template preparation pipeline pages:
// Template Cleaning -> Placeholder Review -> Field Setup.

import type { SuggestionGroup, TemplateResponse, User } from "@/lib/api";

export const FIELD_TYPE_OPTIONS = [
  { label: "Text", value: "text" },
  { label: "Long text", value: "textarea" },
  { label: "Date", value: "date" },
  { label: "Number", value: "number" },
  { label: "List", value: "list" },
  { label: "Signature", value: "signature" },
] as const;

export type FieldTypeValue = (typeof FIELD_TYPE_OPTIONS)[number]["value"];

export const FIELD_TYPE_VALUES = FIELD_TYPE_OPTIONS.map((option) => option.value) as [
  FieldTypeValue,
  ...FieldTypeValue[],
];

export function isFieldType(value: string | null | undefined): value is FieldTypeValue {
  return FIELD_TYPE_OPTIONS.some((option) => option.value === value);
}

export function fieldTypeLabel(value: string): string {
  return FIELD_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export const KEY_PATTERN = /^[a-z][a-z0-9_]*$/;
export const KEY_RULE_MESSAGE =
  "Use lowercase letters, numbers and underscores, starting with a letter (e.g. meeting_date)";

/** Mirror of the backend's suggest_key: normalized snake_case from free text. */
export function suggestKey(raw: string): string {
  let key = raw.trim().replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  key = key.replace(/[\s\-./]+/g, "_");
  key = key.replace(/[^a-z0-9_]/g, "");
  key = key.replace(/_{2,}/g, "_").replace(/^_+|_+$/g, "");
  if (!key) return "";
  if (!/^[a-z]/.test(key)) key = `field_${key}`;
  return key.slice(0, 100);
}

/** 'meeting_date' -> 'Meeting Date'. */
export function keyToLabel(key: string): string {
  const small = new Set(["of", "the", "and", "by", "to", "for", "in", "on", "at"]);
  return key
    .split("_")
    .filter(Boolean)
    .map((part, index) =>
      index > 0 && small.has(part) ? part : part.charAt(0).toUpperCase() + part.slice(1),
    )
    .join(" ");
}

// validation_rule grammar understood by the backend document validator.
const RULE_PART = /^(email|min:\d+|max:\d+)$/;
export const VALIDATION_RULE_MESSAGE =
  "Use email, min:N, max:N or a combination like min:2|max:50";

export function normalizeValidationRule(value: string): string {
  return value
    .split("|")
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
    .join("|");
}

export function isValidValidationRule(value: string): boolean {
  const normalized = normalizeValidationRule(value);
  if (!normalized) return true;
  return normalized.split("|").every((part) => RULE_PART.test(part));
}

export const VALIDATION_PRESETS = [
  { label: "None", value: "" },
  { label: "Email address", value: "email" },
  { label: "Phone (10-20 chars)", value: "min:10|max:20" },
  { label: "At least 1 item / char", value: "min:1" },
  { label: "Short text (max 100)", value: "max:100" },
] as const;

/** Template payload as returned once the access branch adds `can_manage`. */
export type ManagedTemplate = TemplateResponse & { can_manage?: boolean };

/** Editability: the server's can_manage flag, else ownership (pre-merge fallback). */
export function canManageTemplate(
  template: ManagedTemplate | null | undefined,
  user: User | null | undefined,
): boolean {
  if (!template) return false;
  return template.can_manage ?? template.uploaded_by === user?.id;
}

export const GROUP_META: Record<SuggestionGroup, { title: string; description: string }> = {
  fixes: {
    title: "Broken placeholders",
    description: "Existing {{ tokens }} with invalid names that would stop the template from rendering.",
  },
  empty_values: {
    title: "Empty values",
    description: "Labels such as “Date:” with nothing after them — a placeholder is inserted after the label.",
  },
  blanks: {
    title: "Blank lines",
    description: "Underscores, dots or dashes that mark where something is written in.",
  },
  tables: {
    title: "Table cells",
    description: "Empty or sample cells next to a label cell or under a column header.",
  },
  brackets: {
    title: "Bracket hints",
    description: "Hints like [Name], <Date>, {Department} or «Field».",
  },
  filled_values: {
    title: "Sample values",
    description: "Values after a label (e.g. “Venue: Seminar Hall”) or filler text to swap for a placeholder.",
  },
  lists: {
    title: "Lists",
    description: "Numbered or bulleted items that become one list field (each entry renders as an item).",
  },
  detected_values: {
    title: "Possible values in text",
    description: "Dates, times, emails, phone numbers and names found in running text. Lower confidence.",
  },
};

export const GROUP_ORDER: SuggestionGroup[] = [
  "fixes",
  "empty_values",
  "blanks",
  "tables",
  "brackets",
  "filled_values",
  "lists",
  "detected_values",
];

export function confidenceLevel(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

/** Readable message for an API failure on the pipeline pages. */
export function pipelineErrorMessage(
  error: { status?: number; message?: string } | null | undefined,
  action: string,
): string {
  if (!error) return "";
  if (error.status === 403) return `Only template managers can ${action}.`;
  if (error.status === 401) return "Your session has expired. Please log in again.";
  if (error.status === 404) return "This template no longer exists.";
  if (error.status === 409) return error.message || "The template file is missing on the server.";
  return error.message || "Something went wrong. Please try again.";
}
