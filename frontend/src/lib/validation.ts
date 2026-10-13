import { z } from "zod";

/**
 * Client-side validation for document fields. Mirrors the backend validator
 * (backend/app/services/document_validator.py) so that messages and rules
 * match what the server would return:
 * - required: blank / whitespace-only text, or a list with no non-blank item
 * - number: must be a finite number
 * - email: rule "email" (and the email field type)
 * - min:N / max:N: value for numbers, item count for lists, length otherwise
 * Empty optional values skip every other check, as on the server.
 */

export interface ValidationRule {
  email?: boolean;
  min?: number;
  max?: number;
}

export interface ValidatableField {
  field_type: string;
  is_required: boolean;
  validation_rule: string | null;
}

// Same pattern as the backend EMAIL_REGEX.
const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
// Plain decimal numbers (optionally with exponent), like Python float().
const NUMBER_REGEX = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/;

export function parseValidationRule(rule: string | null | undefined): ValidationRule {
  if (!rule) return {};
  const parsed: ValidationRule = {};
  for (const part of rule.split("|")) {
    const trimmed = part.trim();
    if (trimmed === "email") {
      parsed.email = true;
    } else if (trimmed.startsWith("min:") || trimmed.startsWith("max:")) {
      const raw = trimmed.slice(4).trim();
      // Malformed parts (e.g. "min:abc") are ignored, as on the backend.
      if (!/^[+-]?\d+$/.test(raw)) continue;
      const num = parseInt(raw, 10);
      if (trimmed.startsWith("min:")) parsed.min = num;
      else parsed.max = num;
    }
  }
  return parsed;
}

/** Non-blank, trimmed items of a list value. Anything else becomes []. */
export function cleanListItems(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export function parseNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!NUMBER_REGEX.test(trimmed)) return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

export function isValidIsoDate(value: string): boolean {
  if (!ISO_DATE_REGEX.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

/** Whether a field counts as filled in (same rule the backend uses for "required"). */
export function isFieldFilled(fieldType: string, value: unknown): boolean {
  if (fieldType === "list") return cleanListItems(value).length > 0;
  if (value === null || value === undefined) return false;
  return String(value).trim().length > 0;
}

/** Returns the first validation error for a value, or null when it is valid. */
export function validateFieldValue(field: ValidatableField, value: unknown): string | null {
  const rule = parseValidationRule(field.validation_rule);
  const isList = field.field_type === "list";

  if (!isFieldFilled(field.field_type, value)) {
    return field.is_required ? "This field is required" : null;
  }

  if (isList) {
    const count = cleanListItems(value).length;
    if (rule.min !== undefined && count < rule.min) return `Must have at least ${rule.min} items`;
    if (rule.max !== undefined && count > rule.max) return `Must have at most ${rule.max} items`;
    return null;
  }

  const text = String(value);

  if (field.field_type === "number") {
    const num = parseNumber(text);
    if (num === null) return "Must be a valid number";
    if (rule.min !== undefined && num < rule.min) return `Must be at least ${rule.min}`;
    if (rule.max !== undefined && num > rule.max) return `Must be at most ${rule.max}`;
    return null;
  }

  if (field.field_type === "date" && !isValidIsoDate(text.trim())) {
    return "Must be a valid date";
  }

  if ((rule.email || field.field_type === "email") && !EMAIL_REGEX.test(text)) {
    return "Must be a valid email address";
  }
  if (rule.min !== undefined && text.length < rule.min) return `Must be at least ${rule.min} characters`;
  if (rule.max !== undefined && text.length > rule.max) return `Must be at most ${rule.max} characters`;
  return null;
}

export function getFieldSchema(field: ValidatableField): z.ZodTypeAny {
  return z.any().superRefine((value, ctx) => {
    const message = validateFieldValue(field, value);
    if (message) ctx.addIssue({ code: z.ZodIssueCode.custom, message });
  });
}

export function buildFormSchema(fields: Array<ValidatableField & { field_name: string }>) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const field of fields) {
    shape[field.field_name] = getFieldSchema(field);
  }
  // passthrough: never drop values the form holds but the schema doesn't know.
  return z.object(shape).passthrough();
}

/** Short human hint for a field's rules, e.g. "2–5 items" or "Up to 200 characters". */
export function describeValidationRule(field: ValidatableField): string | null {
  const rule = parseValidationRule(field.validation_rule);
  const parts: string[] = [];
  const unit = field.field_type === "list" ? "items" : field.field_type === "number" ? "" : "characters";
  const suffix = unit ? ` ${unit}` : "";
  if (rule.min !== undefined && rule.max !== undefined) {
    parts.push(
      field.field_type === "number"
        ? `Between ${rule.min} and ${rule.max}`
        : `${rule.min}–${rule.max}${suffix}`,
    );
  } else if (rule.min !== undefined) {
    parts.push(field.field_type === "number" ? `At least ${rule.min}` : `At least ${rule.min}${suffix}`);
  } else if (rule.max !== undefined) {
    parts.push(field.field_type === "number" ? `At most ${rule.max}` : `Up to ${rule.max}${suffix}`);
  }
  if (rule.email && field.field_type !== "email") parts.push("Email address");
  return parts.length > 0 ? parts.join(" · ") : null;
}
