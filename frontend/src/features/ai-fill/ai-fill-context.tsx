import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { useAiFill } from "@/hooks/queries";
import type { AiFillProposal, FieldBudget } from "@/lib/api";

/** A proposal the assistant put into the form, and the value it replaced. */
export interface AppliedProposal {
  proposal: AiFillProposal;
  previous: unknown;
}

/**
 * Page-level state of the AI fill assistant (V1.7 P2.2), shared by the chat
 * panel and the form fields. It holds no form values: whether a field is
 * still the AI's is derived from the form (see fill-model.ts).
 */
export interface AiFillAssistant {
  /** The assistant is offered for this draft (AI configured, draft editable). */
  enabled: boolean;
  applied: Readonly<Record<string, AppliedProposal>>;
  /** Fields the user wrote but allowed the AI to change on the next message. */
  unlocked: ReadonlySet<string>;
  /** "Please check" fields the user confirmed. */
  confirmed: ReadonlySet<string>;
  budgets: Readonly<Record<string, FieldBudget>>;
  recordApplied: (entries: Array<{ name: string } & AppliedProposal>) => void;
  /** Forget a field's proposal (after Undo). */
  forget: (name: string) => void;
  setUnlocked: (name: string, unlocked: boolean) => void;
  clearUnlocked: () => void;
  confirm: (name: string) => void;
  /** Forget everything applied (form reset, version restored, chat cleared). */
  reset: () => void;
}

const AiFillContext = createContext<AiFillAssistant | null>(null);

export const AiFillProvider = AiFillContext.Provider;

/** The assistant of the surrounding draft page, or null (create page, previews). */
export function useAiFillAssistantContext(): AiFillAssistant | null {
  return useContext(AiFillContext);
}

export function useAiFillAssistant(documentId: number, enabled: boolean): AiFillAssistant {
  const chat = useAiFill(documentId, enabled);
  const [applied, setApplied] = useState<Record<string, AppliedProposal>>({});
  const [unlocked, setUnlockedState] = useState<ReadonlySet<string>>(new Set());
  const [confirmed, setConfirmed] = useState<ReadonlySet<string>>(new Set());

  const budgets = useMemo(() => {
    const map: Record<string, FieldBudget> = {};
    for (const budget of chat.data?.budgets ?? []) map[budget.field_name] = budget;
    return map;
  }, [chat.data?.budgets]);

  const recordApplied = useCallback((entries: Array<{ name: string } & AppliedProposal>) => {
    if (entries.length === 0) return;
    setApplied((current) => {
      const next = { ...current };
      for (const { name, proposal, previous } of entries) next[name] = { proposal, previous };
      return next;
    });
    // A new value needs a new look.
    setConfirmed((current) => {
      const next = new Set(current);
      for (const { name } of entries) next.delete(name);
      return next;
    });
  }, []);

  const forget = useCallback((name: string) => {
    setApplied((current) => {
      if (!(name in current)) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  }, []);

  const setUnlocked = useCallback((name: string, value: boolean) => {
    setUnlockedState((current) => {
      const next = new Set(current);
      if (value) next.add(name);
      else next.delete(name);
      return next;
    });
  }, []);

  const clearUnlocked = useCallback(() => setUnlockedState(new Set()), []);
  const confirm = useCallback((name: string) => setConfirmed((current) => new Set(current).add(name)), []);
  const reset = useCallback(() => {
    setApplied({});
    setUnlockedState(new Set());
    setConfirmed(new Set());
  }, []);

  return useMemo(
    () => ({ enabled, applied, unlocked, confirmed, budgets, recordApplied, forget, setUnlocked, clearUnlocked, confirm, reset }),
    [enabled, applied, unlocked, confirmed, budgets, recordApplied, forget, setUnlocked, clearUnlocked, confirm, reset],
  );
}

/** Scroll a form field into view and focus its input. */
export function focusFormField(name: string): void {
  requestAnimationFrame(() => {
    const container = document.querySelector<HTMLElement>(`[data-field-name="${CSS.escape(name)}"]`);
    if (!container) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    container.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
    const focusable =
      container.querySelector<HTMLElement>(`#${CSS.escape(`field-${name}`)}`) ??
      container.querySelector<HTMLElement>("input, textarea, select, [contenteditable='true'], button:not([aria-disabled])");
    focusable?.focus({ preventScroll: true });
  });
}
