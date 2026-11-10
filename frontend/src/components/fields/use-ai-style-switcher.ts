import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useFormContext, useWatch } from "react-hook-form";

import { AI_FLAGS_KEY, readAiFlags, withAiFlag, withoutAiFlag } from "@/components/forms/ai-flags";
import { toast } from "@/components/ui/toast";
import {
  aiBlocks,
  applyAiBlocks,
  docToPlain,
  normalizeDoc,
  richValue,
  type RichDoc,
} from "@/features/rich-text/rich-model";
import { useImproveText } from "@/hooks/queries";
import { ApiError, MAX_AI_TEXT_CHARS } from "@/lib/api";
import {
  aiStyleReducer,
  aiTextOf,
  aiTextToList,
  initialAiStyleState,
  measurePlainText,
  normalizeAiResultFor,
  planAiAction,
  sourceTextFor,
  type AiFieldKind,
  type AiStyle,
  type AiStyleState,
  type AiTextMeasure,
} from "./ai-style-state";

// Backend limits for original_items (app/schemas/ai.py).
export const MAX_AI_BLOCKS = 50;
export const MAX_AI_BLOCK_CHARS = 1000;

/** A rich field's switcher text (doc JSON) as its doc. */
export function aiTextToDoc(text: string): RichDoc {
  return normalizeDoc(text ? JSON.parse(text) : null);
}

/** Rich fields: blank / length by the plain text the document shows. */
export const measureRichText: AiTextMeasure = (text) => {
  const plain = text ? docToPlain(aiTextToDoc(text)) : "";
  return { empty: !plain.trim(), length: plain.length };
};

export function measureFor(kind: AiFieldKind): AiTextMeasure {
  return kind === "rich" ? measureRichText : measurePlainText;
}

/** Why a rich text cannot be sent block by block, or null. */
export function richBlocksProblem(text: string): string | null {
  const { items } = aiBlocks(aiTextToDoc(text));
  if (items.length > MAX_AI_BLOCKS) {
    return `AI styles work on up to ${MAX_AI_BLOCKS} paragraphs and list items. This text has ${items.length}.`;
  }
  if (items.some((item) => item.length > MAX_AI_BLOCK_CHARS)) {
    return `AI styles work on paragraphs of up to ${MAX_AI_BLOCK_CHARS.toLocaleString()} characters. Split the longest paragraph first.`;
  }
  return null;
}

/** The form value a switcher text stands for. */
export function aiTextToFormValue(kind: AiFieldKind, text: string): unknown {
  if (kind === "list") return aiTextToList(text);
  if (kind === "rich") return richValue(aiTextToDoc(text));
  return text;
}

/**
 * The request body part for a field: list items, rich paragraphs (non-empty
 * blocks, rewritten one by one so the structure is kept), or plain text.
 */
export function aiSource(kind: AiFieldKind, source: string): { original_items: string[] } | { original_text: string } {
  if (kind === "list") return { original_items: aiTextToList(source) };
  if (kind === "rich") return { original_items: aiBlocks(aiTextToDoc(source)).items };
  return { original_text: source };
}

/** The switcher text of an AI response for the source it was asked about. */
export function aiResultText(
  kind: AiFieldKind,
  source: string,
  response: { improved_text?: string; improved_items?: string[] } | undefined,
): string {
  if (kind === "rich") {
    const doc = aiTextToDoc(source);
    const { indexes } = aiBlocks(doc);
    return JSON.stringify(normalizeDoc(applyAiBlocks(doc, indexes, response?.improved_items ?? [])));
  }
  const raw = kind === "list" && response?.improved_items ? response.improved_items.join("\n") : response?.improved_text ?? "";
  return normalizeAiResultFor(kind, raw);
}

/** Has the text any content (rich: plain projection)? */
function hasContent(kind: AiFieldKind, text: string): boolean {
  return !measureFor(kind)(text).empty;
}

export const AI_STYLE_LABELS: Record<AiStyle, string> = {
  grammar: "Fix grammar",
  tone: "Professional",
  concise: "Concise",
  formal: "Formal",
  expand: "Expand",
};

export interface AiStyleSwitcherOptions {
  fieldName: string;
  fieldLabel: string;
  /**
   * "multiline" keeps line breaks, "text" (one-line input) does not, "list"
   * works on the items (one per line) and rewrites each on its own, and
   * "rich" rewrites the paragraphs and list items of a rich text field one
   * by one, keeping its structure ("Original" restores the exact doc).
   */
  kind: AiFieldKind;
  templateId: number;
  /** Saved draft id, or null before the first save. Read at request time. */
  documentId?: number | null;
}

export interface AiStyleSwitcher {
  state: AiStyleState;
  /** The current field text (as rendered). */
  fieldText: string;
  /** Length of the text the next action would be based on. */
  sourceLength: number;
  /** The field has no text (rich: no text in its paragraphs). */
  isEmpty: boolean;
  isPending: boolean;
  /** Polite screen-reader announcement for the last change. */
  announcement: string;
  runStyle: (style: AiStyle) => void;
  revert: () => void;
}

function errorDetail(err: unknown): string {
  const message = err instanceof Error && err.message ? err.message : "Please try again.";
  // The 503 detail already starts with "AI is currently unavailable: ".
  const detail = message.replace(/^AI is currently unavailable:\s*/, "").trim() || "Please try again.";
  return /[.!?]$/.test(detail) ? detail : `${detail}.`;
}

/**
 * Drives the AI style switcher for one form field. See ai-style-state.ts for
 * the state machine; this hook performs the side effects (request, abort,
 * setValue, toasts) and reads everything through refs so callbacks never act
 * on a stale render.
 */
export function useAiStyleSwitcher(options: AiStyleSwitcherOptions): AiStyleSwitcher {
  const { control, getValues, setValue } = useFormContext();
  const watched = useWatch({ control, name: options.fieldName });
  const fieldText = aiTextOf(options.kind, watched);

  const [state, dispatch] = useReducer(aiStyleReducer, initialAiStyleState);
  const [announcement, setAnnouncement] = useState("");

  // Latest values for async callbacks (avoids stale closures).
  const stateRef = useRef(state);
  stateRef.current = state;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  // Synchronous in-flight guard: two clicks in the same tick both see the
  // same render state, so state alone cannot stop a double request.
  const inFlightRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const requestSeqRef = useRef(0);
  const { mutateAsync: improveText } = useImproveText();
  const improveTextRef = useRef(improveText);
  improveTextRef.current = improveText;

  // Any change to the field value (user typing, form reset, Reset Form)
  // is reported to the state machine.
  useEffect(() => {
    dispatch({ type: "fieldChanged", fieldText });
  }, [fieldText]);

  // The machine dropped a running request (value changed under it): cancel it.
  useEffect(() => {
    if (!state.pending && abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      inFlightRef.current = false;
    }
  }, [state.pending]);

  // Cancel on unmount (navigating away while a request runs).
  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const readFieldText = useCallback((): string => {
    return aiTextOf(optionsRef.current.kind, getValues(optionsRef.current.fieldName));
  }, [getValues]);

  /**
   * Write switcher text into the field. `aiAction` records that AI wrote it
   * (the field's "AI" flag); null means the user's own text is back.
   */
  const writeFieldText = useCallback(
    (text: string, aiAction: AiStyle | null) => {
      const { fieldName, kind } = optionsRef.current;
      const value = aiTextToFormValue(kind, text);
      setValue(fieldName, value, { shouldDirty: true, shouldValidate: true });
      const flags = readAiFlags(getValues());
      setValue(
        AI_FLAGS_KEY,
        aiAction ? withAiFlag(flags, fieldName, aiAction, value) : withoutAiFlag(flags, fieldName),
        { shouldDirty: true },
      );
    },
    [getValues, setValue],
  );

  const runStyle = useCallback(
    async (style: AiStyle) => {
      if (inFlightRef.current) return;
      const opts = optionsRef.current;
      const currentText = readFieldText();
      const plan = planAiAction(stateRef.current, style, currentText, MAX_AI_TEXT_CHARS, measureFor(opts.kind));
      const label = AI_STYLE_LABELS[style];
      if (opts.kind === "rich" && plan.kind === "fetch") {
        const problem = richBlocksProblem(plan.source);
        if (problem) {
          toast({ variant: "destructive", title: "Text is too long for AI", description: problem });
          return;
        }
      }

      switch (plan.kind) {
        case "busy":
        case "empty":
          return;
        case "tooLong":
          toast({
            variant: "destructive",
            title: "Text is too long for AI",
            description: `AI styles work on up to ${MAX_AI_TEXT_CHARS.toLocaleString()} characters. This text has ${plan.length.toLocaleString()}.`,
          });
          return;
        case "cached":
          dispatch({ type: "applyCached", style, source: plan.source, text: plan.text });
          writeFieldText(plan.text, style);
          setAnnouncement(`${label} style applied to ${opts.fieldLabel}.`);
          return;
        case "fetch":
          break;
      }

      const requestId = ++requestSeqRef.current;
      const controller = new AbortController();
      inFlightRef.current = true;
      abortRef.current = controller;
      dispatch({ type: "request", style, requestId, source: plan.source, fieldText: currentText });
      setAnnouncement(`Rewriting ${opts.fieldLabel} in ${label} style…`);

      try {
        const response = await improveTextRef.current({
          payload: {
            template_id: opts.templateId,
            document_id: opts.documentId ?? null,
            field_name: opts.fieldName,
            ...aiSource(opts.kind, plan.source),
            action_type: style,
          },
          signal: controller.signal,
        });
        if (controller.signal.aborted || requestSeqRef.current !== requestId) return;

        const text = aiResultText(opts.kind, plan.source, response);
        if (!hasContent(opts.kind, text)) {
          throw new Error("The AI returned an empty result.");
        }
        // Belt and braces: the field is read-only while a request runs, but if
        // anything changed it meanwhile, never overwrite it.
        if (readFieldText() !== currentText) {
          dispatch({ type: "failure", requestId });
          return;
        }

        dispatch({ type: "success", requestId, text });
        writeFieldText(text, style);
        if (text === plan.source) {
          toast({
            title: "No changes suggested",
            description: `Your text already reads well as "${label}".`,
            duration: 3000,
          });
        }
        setAnnouncement(`${label} style applied to ${opts.fieldLabel}. Choose Original to restore your text.`);
      } catch (err) {
        if (controller.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) {
          dispatch({ type: "failure", requestId });
          return;
        }
        dispatch({ type: "failure", requestId });
        const unavailable = err instanceof ApiError && err.status === 503;
        toast({
          variant: "destructive",
          title: unavailable
            ? "AI is currently unavailable"
            : `Couldn't apply "${label}" to ${opts.fieldLabel}`,
          description: `${errorDetail(err)} Your text was not changed.`,
        });
        setAnnouncement(`${label} style failed. Your text was not changed.`);
      } finally {
        if (requestSeqRef.current === requestId) {
          inFlightRef.current = false;
          if (abortRef.current === controller) abortRef.current = null;
        }
      }
    },
    [readFieldText, writeFieldText],
  );

  const revert = useCallback(() => {
    const current = stateRef.current;
    if (current.pending || current.base === null) return;
    dispatch({ type: "revert" });
    writeFieldText(current.base, null);
    setAnnouncement(`Restored your original text in ${optionsRef.current.fieldLabel}.`);
  }, [writeFieldText]);

  return {
    state,
    fieldText,
    sourceLength: measureFor(options.kind)(sourceTextFor(state, fieldText)).length,
    isEmpty: !hasContent(options.kind, fieldText),
    isPending: state.pending !== null,
    announcement,
    runStyle: (style: AiStyle) => {
      void runStyle(style);
    },
    revert,
  };
}
