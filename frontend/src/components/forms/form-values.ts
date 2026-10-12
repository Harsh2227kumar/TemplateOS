import type { DocumentFormValues, DocumentValue, TemplateField } from "@/lib/api";
import { cleanListItems, isFieldFilled, isValidIsoDate } from "@/lib/validation";

/**
 * Conversions between stored document values (always strings; lists are a
 * JSON array of strings) and react-hook-form values (strings, lists as
 * string[]). Shared by the create and edit pages so both prefill and save
 * every field type the same way.
 */

type FieldLike = Pick<TemplateField, "field_name" | "field_type" | "default_value">;

/** Parses a stored list value. "" -> [], non-JSON text -> [text]. */
export function parseListValue(raw: string | null | undefined): string[] {
  if (raw === null || raw === undefined || !raw.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((item): item is string | number => typeof item === "string" || typeof item === "number").map(String);
    }
  } catch {
    // Not JSON: treat the whole text as one item.
  }
  return [raw];
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toIso(y: number, m: number, d: number): string | null {
  const iso = `${y}-${pad(m)}-${pad(d)}`;
  return isValidIsoDate(iso) ? iso : null;
}

/**
 * Normalises a stored date to the YYYY-MM-DD a date input needs. Accepts ISO
 * dates/datetimes, DD/MM/YYYY or DD-MM-YYYY (day first, as used on Indian
 * university forms) and "12 May 2025" / "May 12, 2025". Anything else is
 * returned unchanged so the user can see and fix it.
 */
export function normalizeDateValue(raw: string | null | undefined): string {
  if (!raw) return "";
  const value = raw.trim();
  if (!value) return "";

  let match = /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$/.exec(value);
  if (match) return toIso(+match[1], +match[2], +match[3]) ?? value;

  match = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(value);
  if (match) return toIso(+match[3], +match[2], +match[1]) ?? value;

  match = /^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\.?,?\s+(\d{4})$/.exec(value);
  if (match) {
    const month = MONTHS.indexOf(match[2].slice(0, 3).toLowerCase());
    if (month >= 0) return toIso(+match[3], month + 1, +match[1]) ?? value;
  }

  match = /^([A-Za-z]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$/.exec(value);
  if (match) {
    const month = MONTHS.indexOf(match[1].slice(0, 3).toLowerCase());
    if (month >= 0) return toIso(+match[3], month + 1, +match[2]) ?? value;
  }

  return value;
}

/** Converts one stored string into the form value for its field type. */
export function toFormValue(fieldType: string, raw: string | null | undefined): string | string[] {
  switch (fieldType) {
    case "list":
      return parseListValue(raw);
    case "date":
      return normalizeDateValue(raw);
    default:
      return raw ?? "";
  }
}

/**
 * Initial form values: field defaults, overridden by saved document values
 * (edit page). Every field gets a value, so the form is never partially
 * uncontrolled and `isDirty` compares against a complete snapshot.
 */
export function buildInitialValues(
  fields: FieldLike[],
  savedValues: Pick<DocumentValue, "field_name" | "value">[] = [],
): DocumentFormValues {
  const values: DocumentFormValues = {};
  for (const field of fields) {
    values[field.field_name] = toFormValue(field.field_type, field.default_value);
  }
  const types = new Map(fields.map((f) => [f.field_name, f.field_type]));
  for (const saved of savedValues) {
    const type = types.get(saved.field_name);
    if (type === undefined) continue; // value for a field that no longer exists
    values[saved.field_name] = toFormValue(type, saved.value);
  }
  return values;
}

/** Converts form values into the backend payload (lists as JSON, blank items dropped). */
export function serializeValues(
  fields: Pick<TemplateField, "field_name" | "field_type">[],
  data: DocumentFormValues,
): Array<{ field_name: string; value: string }> {
  return fields.map((field) => {
    const value = data[field.field_name];
    if (field.field_type === "list") {
      return { field_name: field.field_name, value: JSON.stringify(cleanListItems(value)) };
    }
    const text = value === null || value === undefined ? "" : String(value);
    // Numbers and dates never need surrounding whitespace.
    const trimmed = field.field_type === "number" || field.field_type === "date" ? text.trim() : text;
    return { field_name: field.field_name, value: trimmed };
  });
}

/** Form values as they will be stored, so a later reset() matches the server. */
export function normalizeSavedFormValues(
  fields: Pick<TemplateField, "field_name" | "field_type">[],
  data: DocumentFormValues,
): DocumentFormValues {
  const result: DocumentFormValues = {};
  for (const { field_name, value } of serializeValues(fields, data)) {
    const type = fields.find((f) => f.field_name === field_name)?.field_type ?? "text";
    result[field_name] = toFormValue(type, value);
  }
  return result;
}

export function countRequiredFilled(
  fields: Pick<TemplateField, "field_name" | "field_type" | "is_required">[],
  values: DocumentFormValues,
): { filled: number; total: number } {
  let filled = 0;
  let total = 0;
  for (const field of fields) {
    if (!field.is_required) continue;
    total += 1;
    if (isFieldFilled(field.field_type, values[field.field_name])) filled += 1;
  }
  return { filled, total };
}

/** Groups fields by section, keeping display order (sections in first-seen order). */
export function groupFieldsBySection<T extends Pick<TemplateField, "section" | "display_order">>(
  fields: T[],
): Array<{ name: string; fields: T[] }> {
  const ordered = fields
    .map((field, index) => ({ field, index }))
    .sort((a, b) => (a.field.display_order ?? 0) - (b.field.display_order ?? 0) || a.index - b.index)
    .map(({ field }) => field);
  const groups = new Map<string, T[]>();
  for (const field of ordered) {
    const name = field.section?.trim() || "General";
    const list = groups.get(name);
    if (list) list.push(field);
    else groups.set(name, [field]);
  }
  return Array.from(groups, ([name, list]) => ({ name, fields: list }));
}
