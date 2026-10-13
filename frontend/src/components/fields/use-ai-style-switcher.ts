import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useFormContext, useWatch } from "react-hook-form";

import { toast } from "@/components/ui/toast";
import { useImproveText } from "@/hooks/queries";
import { ApiError, MAX_AI_TEXT_CHARS } from "@/lib/api";
import {
  aiStyleReducer,
  initialAiStyleState,
  normalizeAiResult,
  planAiAction,
  sourceTextFor,
  type AiStyle,
  type AiStyleState,
} from "./ai-style-state";

export const AI_STYLE_LABELS: Record<AiStyle, string> = {
  grammar: "Fix grammar",
  tone: "Professional",
  concise: "Concise",
  formal: "Formal",
};

export interface AiStyleSwitcherOptions {
  fieldName: string;
  fieldLabel: string;
  /** textarea (true) keeps line breaks; a single-line input does not. */
  multiline: boolean;
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
  const fieldText = typeof watched === "string" ? watched : "";

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
    const value = getValues(optionsRef.current.fieldName);
    return typeof value === "string" ? value : "";
  }, [getValues]);

  const writeFieldText = useCallback(
    (text: string) => {
      setValue(optionsRef.current.fieldName, text, { shouldDirty: true, shouldValidate: true });
    },
    [setValue],
  );

  const runStyle = useCallback(
    async (style: AiStyle) => {
      if (inFlightRef.current) return;
      const opts = optionsRef.current;
      const currentText = readFieldText();
      const plan = planAiAction(stateRef.current, style, currentText, MAX_AI_TEXT_CHARS);
      const label = AI_STYLE_LABELS[style];

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
          writeFieldText(plan.text);
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
            original_text: plan.source,
            action_type: style,
          },
          signal: controller.signal,
        });
        if (controller.signal.aborted || requestSeqRef.current !== requestId) return;

        const text = normalizeAiResult(response?.improved_text ?? "", opts.multiline);
        if (!text.trim()) {
          throw new Error("The AI returned an empty result.");
        }
        // Belt and braces: the field is read-only while a request runs, but if
        // anything changed it meanwhile, never overwrite it.
        if (readFieldText() !== currentText) {
          dispatch({ type: "failure", requestId });
          return;
        }

        dispatch({ type: "success", requestId, text });
        writeFieldText(text);
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
    writeFieldText(current.base);
    setAnnouncement(`Restored your original text in ${optionsRef.current.fieldLabel}.`);
  }, [writeFieldText]);

  return {
    state,
    fieldText,
    sourceLength: sourceTextFor(state, fieldText).length,
    isPending: state.pending !== null,
    announcement,
    runStyle: (style: AiStyle) => {
      void runStyle(style);
    },
    revert,
  };
}
