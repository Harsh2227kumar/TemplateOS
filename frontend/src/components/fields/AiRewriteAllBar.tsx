import { useEffect, useRef, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Loader2, Sparkles, Undo2 } from "lucide-react";

import { AI_FLAGS_KEY, readAiFlags, withAiFlag, withoutAiFlag } from "@/components/forms/ai-flags";
import { toast } from "@/components/ui/toast";
import { useImproveText } from "@/hooks/queries";
import { ApiError, MAX_AI_TEXT_CHARS, type TemplateField } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  aiFieldKind,
  planRewriteAll,
  sameFieldValue,
  type AiStyle,
  type RewriteAllTarget,
} from "./ai-style-state";
import { AI_STYLES } from "./AiActionToolbar";
import {
  AI_STYLE_LABELS,
  aiResultText,
  aiSource,
  aiTextToFormValue,
  measureFor,
  richBlocksProblem,
} from "./use-ai-style-switcher";

// Requests in flight at once: fast enough, gentle on the Bedrock quota.
const CONCURRENCY = 3;

interface AiRewriteAllBarProps {
  fields: TemplateField[];
  templateId: number;
  /** Saved draft id, or null before the first save. */
  documentId?: number | null;
  disabled?: boolean;
}

interface LastRun {
  style: AiStyle;
  /** Per field: the value before and after the rewrite (for Undo). */
  changes: { fieldName: string; before: unknown; after: unknown }[];
}

/**
 * One AI action for the whole draft: rewrites every AI-enabled field that has
 * content in the chosen style (lists item by item), then offers Undo. Only
 * the field values change, so the generated document keeps the template's
 * own formatting. A field edited while the rewrite runs is left alone.
 */
export function AiRewriteAllBar({ fields, templateId, documentId, disabled = false }: AiRewriteAllBarProps) {
  const { getValues, setValue } = useFormContext();
  const { mutateAsync: improveText } = useImproveText();
  const [running, setRunning] = useState<{ style: AiStyle; done: number; total: number } | null>(null);
  const [lastRun, setLastRun] = useState<LastRun | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const aiFieldCount = fields.filter((f) => f.ai_enabled && aiFieldKind(f.field_type) !== null).length;
  if (aiFieldCount === 0) return null;

  const labelOf = (fieldName: string) =>
    fields.find((f) => f.field_name === fieldName)?.field_label?.trim() || fieldName;

  const rewrite = async (target: RewriteAllTarget, style: AiStyle, signal: AbortSignal): Promise<unknown> => {
    if (target.kind === "rich") {
      const problem = richBlocksProblem(target.text);
      if (problem) throw new Error(problem);
    }
    const response = await improveText({
      payload: {
        template_id: templateId,
        document_id: documentId ?? null,
        field_name: target.fieldName,
        ...aiSource(target.kind, target.text),
        action_type: style,
      },
      signal,
    });
    const text = aiResultText(target.kind, target.text, response);
    if (measureFor(target.kind)(text).empty) throw new Error("The AI returned an empty result.");
    return aiTextToFormValue(target.kind, text);
  };

  /** Mark (or unmark) fields as AI-written after values changed. */
  const updateFlags = (changes: { fieldName: string; value: unknown; action: AiStyle | null }[]) => {
    let flags = readAiFlags(getValues());
    for (const { fieldName, value, action } of changes) {
      flags = action ? withAiFlag(flags, fieldName, action, value) : withoutAiFlag(flags, fieldName);
    }
    setValue(AI_FLAGS_KEY, flags, { shouldDirty: true });
  };

  const run = async (style: AiStyle) => {
    if (running || disabled) return;
    const plan = planRewriteAll(fields, getValues(), style, MAX_AI_TEXT_CHARS, measureFor);
    if (plan.targets.length === 0) {
      toast({
        title: "Nothing to rewrite",
        description:
          style === "expand"
            ? "Expand works on paragraph and list fields. Fill in an AI-enabled one first."
            : "Fill in the AI-enabled fields first.",
        duration: 3500,
      });
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setRunning({ style, done: 0, total: plan.targets.length });
    const changes: LastRun["changes"] = [];
    const errors: unknown[] = [];
    let skippedEdited = 0;
    let next = 0;

    const worker = async () => {
      while (next < plan.targets.length && !controller.signal.aborted) {
        const target = plan.targets[next++];
        try {
          const after = await rewrite(target, style, controller.signal);
          if (controller.signal.aborted) return;
          // The user edited this field meanwhile: keep their edit.
          if (!sameFieldValue(getValues(target.fieldName), target.value)) {
            skippedEdited += 1;
          } else if (!sameFieldValue(after, target.value)) {
            setValue(target.fieldName, after, { shouldDirty: true, shouldValidate: true });
            changes.push({ fieldName: target.fieldName, before: target.value, after });
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          errors.push(err);
        }
        setRunning((current) => (current ? { ...current, done: current.done + 1 } : current));
      }
    };

    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, plan.targets.length) }, worker));
    if (controller.signal.aborted) return;
    updateFlags(changes.map((change) => ({ fieldName: change.fieldName, value: change.after, action: style })));
    abortRef.current = null;
    setRunning(null);
    setLastRun(changes.length > 0 ? { style, changes } : null);

    const label = AI_STYLE_LABELS[style];
    if (errors.length === plan.targets.length) {
      const first = errors[0];
      const unavailable = first instanceof ApiError && first.status === 503;
      toast({
        variant: "destructive",
        title: unavailable ? "AI is currently unavailable" : `Couldn't apply "${label}"`,
        description: `${first instanceof Error && first.message ? first.message : "Please try again."} Nothing was changed.`,
      });
      return;
    }
    const parts = [
      changes.length === 1 ? "1 field rewritten" : `${changes.length} fields rewritten`,
      errors.length > 0 ? `${errors.length} failed` : null,
      skippedEdited > 0 ? `${skippedEdited} skipped because you edited them` : null,
    ].filter(Boolean);
    toast({
      variant: errors.length > 0 ? "destructive" : undefined,
      title: changes.length > 0 ? `"${label}" applied` : "No changes suggested",
      description: `${parts.join(", ")}. Review the text, then save.`,
      duration: 4000,
    });
  };

  const undo = () => {
    if (!lastRun || running) return;
    let restored = 0;
    const undone: { fieldName: string; value: unknown; action: null }[] = [];
    for (const change of lastRun.changes) {
      // Only undo fields still showing the AI result.
      if (sameFieldValue(getValues(change.fieldName), change.after)) {
        setValue(change.fieldName, change.before, { shouldDirty: true, shouldValidate: true });
        undone.push({ fieldName: change.fieldName, value: change.before, action: null });
        restored += 1;
      }
    }
    if (undone.length) updateFlags(undone);
    setLastRun(null);
    toast({
      title: restored > 0 ? "AI changes undone" : "Nothing to undo",
      description:
        restored > 0
          ? `Restored ${restored === 1 ? "1 field" : `${restored} fields`} (${lastRun.changes.map((c) => labelOf(c.fieldName)).join(", ")}).`
          : "The rewritten fields have been edited since.",
      duration: 3500,
    });
  };

  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/70 p-3" aria-busy={running !== null}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 flex items-center gap-1 text-sm font-semibold text-violet-800">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Rewrite all with AI
        </span>
        {AI_STYLES.map(({ style, icon, hint }) => {
          const isRunning = running?.style === style;
          return (
            <button
              key={style}
              type="button"
              title={hint}
              onClick={() => void run(style)}
              disabled={disabled || running !== null}
              className={cn(
                "inline-flex h-8 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-1",
                "border-violet-200 bg-white text-violet-800 hover:border-violet-300 hover:bg-violet-100",
                "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-white",
                isRunning && "cursor-progress border-violet-400 bg-violet-100 disabled:opacity-100",
              )}
            >
              {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : icon}
              {AI_STYLE_LABELS[style]}
            </button>
          );
        })}
        {lastRun && !running && (
          <button
            type="button"
            onClick={undo}
            className="ml-auto inline-flex h-8 items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
          >
            <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
            Undo {AI_STYLE_LABELS[lastRun.style]}
          </button>
        )}
      </div>
      <p className="mt-1.5 text-xs leading-snug text-violet-900/80" aria-live="polite">
        {running
          ? `Rewriting ${running.done} of ${running.total} fields as ${AI_STYLE_LABELS[running.style]}…`
          : lastRun
            ? `${AI_STYLE_LABELS[lastRun.style]} applied to ${lastRun.changes.length === 1 ? "1 field" : `${lastRun.changes.length} fields`}. Review, then save, or undo.`
            : `Rewrites all ${aiFieldCount === 1 ? "AI-enabled field" : `${aiFieldCount} AI-enabled fields`} at once (lists item by item, paragraphs one by one). The document keeps the template's formatting.`}
      </p>
    </div>
  );
}
