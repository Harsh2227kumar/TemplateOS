/**
 * Which field values were written by AI (V1.7 Phase 2: ai_modified /
 * ai_action, saved per value and shown as an "AI" badge).
 *
 * The form keeps one entry per AI-written field under AI_FLAGS_KEY:
 * { action, fingerprint } where the fingerprint identifies the exact value
 * the AI produced. A field counts as AI-modified only while its value still
 * has that fingerprint, so:
 * - applying an AI style sets the entry (action + the new value)
 * - any manual edit changes the value -> no longer AI-modified
 * - "Original" / undo restore the user's value -> no longer AI-modified
 * - Reset Form / prefill / restore put back the saved entries with the
 *   saved values -> AI-modified again
 * No event ordering is involved: the flag is derived from value + entry.
 *
 * Kept free of React and `@/` imports so it can be unit tested with
 * `node --test` (frontend/tests/ai-flags.test.ts).
 */

export type AiFlagAction = "grammar" | "tone" | "concise" | "formal" | "expand";

/** Form key of the entries. "$" cannot appear in a template field name. */
export const AI_FLAGS_KEY = "$aiFlags";

export interface AiFlag {
  action: AiFlagAction;
  fingerprint: string;
}

export type AiFlags = Record<string, AiFlag>;

export interface AiFlagState {
  ai_modified: boolean;
  ai_action: AiFlagAction | null;
}

const NOT_MODIFIED: AiFlagState = { ai_modified: false, ai_action: null };

/** A stable identity of a form value (text, list items, or rich doc). */
export function aiFingerprint(value: unknown): string {
  if (Array.isArray(value)) {
    const items = value.map((item) => (typeof item === "string" ? item.trim() : "")).filter(Boolean);
    return `list:${JSON.stringify(items)}`;
  }
  if (value !== null && typeof value === "object") {
    const doc = (value as { doc?: unknown }).doc ?? value;
    return `rich:${JSON.stringify(doc)}`;
  }
  return `text:${value === null || value === undefined ? "" : String(value)}`;
}

/** The entries held in the form values (none -> {}). */
export function readAiFlags(values: Record<string, unknown> | null | undefined): AiFlags {
  const raw = values?.[AI_FLAGS_KEY];
  return raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as AiFlags) : {};
}

/** ai_modified / ai_action of a field for its current value. */
export function aiFlagFor(flags: AiFlags, fieldName: string, value: unknown): AiFlagState {
  const flag = flags[fieldName];
  if (!flag || flag.fingerprint !== aiFingerprint(value)) return NOT_MODIFIED;
  return { ai_modified: true, ai_action: flag.action };
}

/** Entries after AI wrote `value` into the field with `action`. */
export function withAiFlag(flags: AiFlags, fieldName: string, action: AiFlagAction, value: unknown): AiFlags {
  return { ...flags, [fieldName]: { action, fingerprint: aiFingerprint(value) } };
}

/** Entries without the field (the user's own value is back). */
export function withoutAiFlag(flags: AiFlags, fieldName: string): AiFlags {
  if (!(fieldName in flags)) return flags;
  const next = { ...flags };
  delete next[fieldName];
  return next;
}

/**
 * Entries for values as loaded from the server: one per value saved with
 * ai_modified (and an action), fingerprinted with its form value.
 */
export function savedAiFlags(
  saved: Array<{ field_name: string; ai_modified?: boolean; ai_action?: AiFlagAction | null }>,
  formValues: Record<string, unknown>,
): AiFlags {
  const flags: AiFlags = {};
  for (const value of saved) {
    if (value.ai_modified && value.ai_action && value.field_name in formValues) {
      flags[value.field_name] = { action: value.ai_action, fingerprint: aiFingerprint(formValues[value.field_name]) };
    }
  }
  return flags;
}

/**
 * After saving: the entries that were in effect, re-fingerprinted with the
 * values as stored (e.g. list items trimmed), so the badge survives the save.
 */
export function carryAiFlags(
  flags: AiFlags,
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): AiFlags {
  const next: AiFlags = {};
  for (const [fieldName, flag] of Object.entries(flags)) {
    if (aiFlagFor(flags, fieldName, before[fieldName]).ai_modified && fieldName in after) {
      next[fieldName] = { action: flag.action, fingerprint: aiFingerprint(after[fieldName]) };
    }
  }
  return next;
}
