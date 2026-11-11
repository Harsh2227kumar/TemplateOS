import { useFormContext, useWatch } from "react-hook-form";
import { AlertTriangle, Check, Lock, LockOpen, Undo2 } from "lucide-react";

import { AI_FLAGS_KEY, readAiFlags } from "@/components/forms/ai-flags";

import { useAiFillAssistantContext } from "./ai-fill-context";
import { fieldOrigin, overBudget, undoProposal } from "./fill-model";

const linkButton =
  "inline-flex items-center gap-1 rounded text-xs font-medium underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500";

/**
 * Under a form field on the draft page: what the AI fill assistant did with
 * it (V1.7 P2.2). "Please check" for medium-confidence values, the user's
 * own words the value came from, Undo, the lock on fields the user edited,
 * and a hint when the value is longer than its place in the document.
 * Renders nothing outside a draft page with the assistant.
 */
export function AiFillFieldNote({ name, fieldType }: { name: string; fieldType: string }) {
  const assistant = useAiFillAssistantContext();
  const { control, getValues, setValue } = useFormContext();
  const value = useWatch({ control, name });
  const flagsValue = useWatch({ control, name: AI_FLAGS_KEY });
  if (!assistant?.enabled) return null;

  const entry = assistant.applied[name];
  const origin = fieldOrigin(fieldType, value, readAiFlags({ [AI_FLAGS_KEY]: flagsValue }), name);
  const tooLong = overBudget(fieldType, value, assistant.budgets[name]);
  const isAiValue = Boolean(entry) && origin === "ai";
  const needsCheck = isAiValue && entry.proposal.confidence === "medium" && !assistant.confirmed.has(name);
  const editedByUser = Boolean(entry) && origin === "user";
  const unlocked = assistant.unlocked.has(name);
  if (!isAiValue && !editedByUser && !tooLong) return null;

  const undo = () => {
    if (!entry) return;
    const next = undoProposal(getValues(), name, entry.previous);
    setValue(name, next[name], { shouldDirty: true, shouldValidate: true });
    setValue(AI_FLAGS_KEY, next[AI_FLAGS_KEY], { shouldDirty: true });
    assistant.forget(name);
  };

  return (
    <div className="space-y-1" data-ai-fill-note={name}>
      {needsCheck && (
        <div className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
          <span className="flex min-w-0 flex-1 items-start gap-1.5">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />
            <span className="break-words">
              <span className="font-semibold">Please check.</span> {entry.proposal.reason || "The AI was not fully sure about this."}
            </span>
          </span>
          <button type="button" onClick={() => assistant.confirm(name)} className={`${linkButton} text-amber-900`}>
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
            Looks right
          </button>
        </div>
      )}

      {isAiValue && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          {entry.proposal.source_text && (
            <details className="min-w-0 flex-1">
              <summary className="cursor-pointer select-none text-violet-700 hover:underline">Your words</summary>
              <p className="mt-1 break-words rounded bg-slate-50 px-2 py-1 italic text-slate-600">
                “{entry.proposal.source_text}”
              </p>
            </details>
          )}
          <button type="button" onClick={undo} className={`${linkButton} text-slate-600`} title="Put back what was here before the AI">
            <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
            Undo AI
          </button>
        </div>
      )}

      {editedByUser && (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
          {unlocked ? (
            <>
              <LockOpen className="h-3.5 w-3.5 text-violet-600" aria-hidden="true" />
              The AI may update this with your next message.
              <button type="button" onClick={() => assistant.setUnlocked(name, false)} className={`${linkButton} text-slate-700`}>
                Keep mine
              </button>
            </>
          ) : (
            <>
              <Lock className="h-3.5 w-3.5" aria-hidden="true" />
              You edited this, so the AI will leave it alone.
              <button type="button" onClick={() => assistant.setUnlocked(name, true)} className={`${linkButton} text-violet-700`}>
                Let AI update
              </button>
            </>
          )}
        </p>
      )}

      {tooLong && (
        <p className="flex items-start gap-1.5 text-xs text-amber-800" role="status">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />
          <span>
            Too long for its space in the document ({tooLong.length.toLocaleString()} / {tooLong.budget.toLocaleString()}{" "}
            {tooLong.unit === "items" ? "items" : "characters"}). Shorten it, or fix the layout in Word after generating.
          </span>
        </p>
      )}
    </div>
  );
}
