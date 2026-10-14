/**
 * Pure state machine behind the per-field AI style switcher.
 *
 * Every AI style is applied to the user's OWN text (`base`), never to the
 * output of a previous AI rewrite. That is what makes the toolbar behave like
 * a style switcher: Formal -> Concise gives "concise version of what the user
 * wrote", not "concise version of the formal version". `base` stays fixed
 * until the user edits the field again (or the form is reset), at which point
 * the edited text becomes the new user text.
 *
 * Kept free of React and runtime imports so it can be unit tested with
 * `node --test` (see frontend/tests).
 */

export type AiStyle = "grammar" | "tone" | "concise" | "formal" | "expand";

export interface AiStyleState {
  /** The user's own text that the applied style was generated from. */
  base: string | null;
  /** The style currently shown in the field, and the exact text it produced. */
  applied: { style: AiStyle; text: string } | null;
  /** Results already generated for `cacheFor`, so switching back is instant. */
  cache: Partial<Record<AiStyle, string>>;
  cacheFor: string | null;
  /** The request in flight, if any. `fieldText` is the field value when it started. */
  pending: { style: AiStyle; requestId: number; source: string; fieldText: string } | null;
}

export const initialAiStyleState: AiStyleState = {
  base: null,
  applied: null,
  cache: {},
  cacheFor: null,
  pending: null,
};

export type AiStyleEvent =
  | { type: "request"; style: AiStyle; requestId: number; source: string; fieldText: string }
  | { type: "success"; requestId: number; text: string }
  | { type: "failure"; requestId: number }
  | { type: "applyCached"; style: AiStyle; source: string; text: string }
  | { type: "fieldChanged"; fieldText: string }
  | { type: "revert" }
  | { type: "reset" };

/**
 * The text an AI action should be based on, given what is in the field now.
 * While the field still shows an unedited AI result, that is the user's
 * original text; otherwise it is whatever the field contains.
 */
export function sourceTextFor(state: AiStyleState, fieldText: string): string {
  if (state.applied && state.base !== null && fieldText === state.applied.text) {
    return state.base;
  }
  return fieldText;
}

export type AiActionPlan =
  | { kind: "busy" }
  | { kind: "empty" }
  | { kind: "tooLong"; length: number }
  | { kind: "cached"; source: string; text: string }
  | { kind: "fetch"; source: string };

/** Decides what clicking `style` should do. Pure: the caller performs it. */
export function planAiAction(
  state: AiStyleState,
  style: AiStyle,
  fieldText: string,
  maxChars: number,
): AiActionPlan {
  if (state.pending) return { kind: "busy" };
  const source = sourceTextFor(state, fieldText);
  if (!source.trim()) return { kind: "empty" };
  if (source.length > maxChars) return { kind: "tooLong", length: source.length };
  // Clicking the style that is already applied asks for a fresh variation.
  const isActive = state.applied?.style === style && fieldText === state.applied.text;
  const cached = state.cacheFor === source ? state.cache[style] : undefined;
  if (!isActive && cached !== undefined) return { kind: "cached", source, text: cached };
  return { kind: "fetch", source };
}

function apply(state: AiStyleState, style: AiStyle, source: string, text: string): AiStyleState {
  const cache = state.cacheFor === source ? state.cache : {};
  return {
    base: source,
    applied: { style, text },
    cache: { ...cache, [style]: text },
    cacheFor: source,
    pending: null,
  };
}

export function aiStyleReducer(state: AiStyleState, event: AiStyleEvent): AiStyleState {
  switch (event.type) {
    case "request":
      if (state.pending) return state;
      return {
        ...state,
        pending: {
          style: event.style,
          requestId: event.requestId,
          source: event.source,
          fieldText: event.fieldText,
        },
      };

    case "success":
      if (!state.pending || state.pending.requestId !== event.requestId) return state;
      return apply(state, state.pending.style, state.pending.source, event.text);

    case "failure":
      if (!state.pending || state.pending.requestId !== event.requestId) return state;
      return { ...state, pending: null };

    case "applyCached":
      if (state.pending) return state;
      return apply(state, event.style, event.source, event.text);

    case "fieldChanged": {
      let next = state;
      // The value changed under a running request (form reset, programmatic
      // update): the result would be stale, so drop the request.
      if (next.pending && event.fieldText !== next.pending.fieldText) {
        next = { ...next, pending: null };
      }
      // The user edited the AI result: their edit is now "their text".
      if (next.applied && event.fieldText !== next.applied.text) {
        next = { ...next, base: null, applied: null };
      }
      return next;
    }

    case "revert":
      if (state.pending || state.base === null) return state;
      // Keep the cache: it still belongs to the restored text.
      return { ...state, base: null, applied: null };

    case "reset":
      return initialAiStyleState;
  }
}

/**
 * Cleans an AI result for the target input. Single-line text inputs cannot
 * hold newlines, so they are collapsed to spaces there.
 */
export function normalizeAiResult(text: string, multiline: boolean): string {
  if (multiline) return text.replace(/\r\n/g, "\n").trim();
  return text.replace(/\s*[\r\n]+\s*/g, " ").trim();
}

// ── Which fields AI applies to, and list fields as text ──────────────────

/** How AI treats a field type: one line, paragraphs, or one item per line. */
export type AiFieldKind = "text" | "multiline" | "list";

/** The AI kind for a field type, or null when AI does not apply to it. */
export function aiFieldKind(fieldType: string): AiFieldKind | null {
  if (fieldType === "text") return "text";
  if (fieldType === "textarea") return "multiline";
  if (fieldType === "list") return "list";
  return null;
}

/** Field types the AI-enabled switch has an effect on. */
export const AI_FIELD_TYPES: readonly string[] = ["text", "textarea", "list"];

/**
 * A list value as the text the style switcher works on: one item per line.
 * Blank rows are kept so the text tracks the field exactly while editing.
 */
export function listToAiText(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value.map((item) => (typeof item === "string" ? item : item == null ? "" : String(item))).join("\n");
}

/** Non-blank, trimmed items of switcher text (inverse of listToAiText). */
export function aiTextToList(text: string): string[] {
  return text
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

/** The value of any AI field as switcher text. */
export function aiTextOf(kind: AiFieldKind, value: unknown): string {
  if (kind === "list") return listToAiText(value);
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

/** Cleans an AI result for a field kind (lists: one trimmed item per line). */
export function normalizeAiResultFor(kind: AiFieldKind, text: string): string {
  if (kind === "list") return aiTextToList(text).join("\n");
  return normalizeAiResult(text, kind === "multiline");
}

/** Expanding a one-line input would only produce a run-on line. */
export function styleAppliesTo(style: AiStyle, kind: AiFieldKind): boolean {
  return style !== "expand" || kind !== "text";
}

// ── "Rewrite all with AI" ─────────────────────────────────────────────────

export interface RewriteAllField {
  field_name: string;
  field_type: string;
  ai_enabled?: boolean;
}

export interface RewriteAllTarget {
  fieldName: string;
  kind: AiFieldKind;
  /** The field value when planned; a result is applied only if it is unchanged. */
  value: unknown;
  /** Switcher text of `value`. */
  text: string;
}

export interface RewriteAllPlan {
  targets: RewriteAllTarget[];
  /** AI fields left out because they are blank, too long, or the style does not apply. */
  skipped: { fieldName: string; reason: "empty" | "tooLong" | "notApplicable" }[];
}

/** Which AI-enabled fields a document-wide rewrite in `style` would change. */
export function planRewriteAll(
  fields: RewriteAllField[],
  values: Record<string, unknown>,
  style: AiStyle,
  maxChars: number,
): RewriteAllPlan {
  const plan: RewriteAllPlan = { targets: [], skipped: [] };
  for (const field of fields) {
    const kind = aiFieldKind(field.field_type);
    if (!field.ai_enabled || kind === null) continue;
    const value = values[field.field_name];
    const text = aiTextOf(kind, value);
    if (!styleAppliesTo(style, kind)) {
      plan.skipped.push({ fieldName: field.field_name, reason: "notApplicable" });
    } else if (!text.trim()) {
      plan.skipped.push({ fieldName: field.field_name, reason: "empty" });
    } else if (text.length > maxChars) {
      plan.skipped.push({ fieldName: field.field_name, reason: "tooLong" });
    } else {
      plan.targets.push({ fieldName: field.field_name, kind, value, text });
    }
  }
  return plan;
}

/** True when two form values are the same (strings, or lists item by item). */
export function sameFieldValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, i) => item === b[i]);
  }
  return (a ?? "") === (b ?? "");
}
