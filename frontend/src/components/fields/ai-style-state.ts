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

export type AiStyle = "grammar" | "tone" | "concise" | "formal";

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
