import { CheckCircle2, Eraser, Eye, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { MonoKey, Notice } from "@/components/fields/pipeline-ui";
import type { CleanPreviewResponse } from "@/lib/api";

import { HighlightedText } from "./HighlightedText";
import type { CleaningSession } from "./use-cleaning-session";

/** Sticky bar with the change count, warnings and the Preview / Apply buttons. */
export function ApplyBar({
  session,
  previewLoading,
  isApplying,
  onPreview,
  onApply,
}: {
  session: CleaningSession;
  previewLoading: boolean;
  isApplying: boolean;
  onPreview: () => void;
  onApply: () => void;
}) {
  const { changeCount, accepted, manual, blockingProblem, typeConflicts } = session;
  return (
    <div className="sticky bottom-0 z-30 rounded-t-xl border bg-white/95 px-4 py-3 shadow-lg backdrop-blur">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-sm">
          <p className="font-medium text-slate-900">
            {changeCount} change{changeCount === 1 ? "" : "s"} ready
            {accepted.length > 0 && manual.length > 0 ? ` (${accepted.length} suggested, ${manual.length} manual)` : ""}
          </p>
          {blockingProblem && changeCount > 0 && <p className="text-xs text-red-600">{blockingProblem}</p>}
          {!blockingProblem && typeConflicts.length > 0 && (
            <p className="text-xs text-amber-700">
              {typeConflicts.join(", ")} {typeConflicts.length === 1 ? "has" : "have"} different types — the first
              one wins.
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" disabled={!!blockingProblem || previewLoading} onClick={onPreview}>
            {previewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Preview
          </Button>
          <Button className="gap-2" disabled={!!blockingProblem || isApplying} onClick={onApply}>
            {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eraser className="h-4 w-4" />}
            Apply cleaning
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Dry-run result: the cleaned text with placeholders highlighted. */
export function CleanPreviewDialog({
  open,
  onOpenChange,
  preview,
  loading,
  error,
  canApply,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: CleanPreviewResponse | null;
  loading: boolean;
  error: string | null;
  canApply: boolean;
  onApply: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Preview of the cleaned template</DialogTitle>
          <DialogDescription>Nothing is saved yet. Placeholders are highlighted.</DialogDescription>
        </DialogHeader>
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-5/6" />
            <Skeleton className="h-6 w-4/6" />
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        {preview && !loading && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              {preview.detected_keys.length} placeholder{preview.detected_keys.length === 1 ? "" : "s"}:{" "}
              {preview.detected_keys.map((key) => (
                <MonoKey key={key} name={key} className="mr-1 mt-1" />
              ))}
            </p>
            {preview.warnings.render_error && (
              <Notice tone="error" title="This would not render">{preview.warnings.render_error}</Notice>
            )}
            {preview.results.some((r) => !r.matched) && (
              <Notice tone="warning" title="Some changes cannot be applied">
                {preview.results
                  .filter((r) => !r.matched)
                  .map((r) => r.placeholder_key)
                  .join(", ")}
              </Notice>
            )}
            <div className="max-h-[50vh] space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-3">
              {preview.segments.map((segment) => (
                <p key={segment.index} className="whitespace-pre-wrap break-words text-sm text-slate-700">
                  {segment.location !== "body" && (
                    <span className="mr-2 text-[10px] uppercase text-slate-400">{segment.location}</span>
                  )}
                  <HighlightedText text={segment.text} />
                </p>
              ))}
            </div>
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Keep editing
          </Button>
          <Button disabled={!preview || loading || !canApply} onClick={onApply}>
            Looks good — apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Final confirmation listing every replacement. */
export function ApplyCleaningDialog({
  open,
  onOpenChange,
  session,
  hasProcessed,
  isApplying,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  session: CleaningSession;
  hasProcessed: boolean;
  isApplying: boolean;
  onConfirm: () => void;
}) {
  const { changeCount, accepted, manual, decisions } = session;
  return (
    <Dialog open={open} onOpenChange={(next) => !isApplying && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Apply cleaning?</DialogTitle>
          <DialogDescription>
            {changeCount} change{changeCount === 1 ? "" : "s"} will be written to a processed copy. Your original
            file is preserved.
            {hasProcessed ? " The existing processed copy will be replaced." : ""}
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
          {accepted.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 max-w-[60%] truncate text-slate-600">
                {s.sample_text ? `“${s.sample_text.split("\n")[0]}”` : "(empty spot)"}
              </span>
              <span className="text-slate-400">→</span>
              <MonoKey name={decisions[s.id].key} />
            </li>
          ))}
          {manual.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 max-w-[60%] truncate text-slate-600">“{m.sample_text}”</span>
              <span className="text-slate-400">→</span>
              <MonoKey name={m.placeholder_key} />
            </li>
          ))}
        </ul>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isApplying}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={isApplying} className="gap-2">
            {isApplying ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Applying…
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" />
                Confirm and apply
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
