import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { History, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { useRestoreTemplateRevision, useTemplateRevisions } from "@/hooks/queries/word-editor-actions";
import type { TemplateRevision } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

import { restoreRevisionConfirmText, revisionChangeText, revisionSourceLabel } from "./editor-review-model";

function relativeTime(value: string): string {
  const date = parseServerDate(value);
  return date ? formatDistanceToNow(date, { addSuffix: true }) : "";
}

/** V1.7 P2.1: the template file's history; managers can make an older revision current. */
export function TemplateRevisionsPanel({ templateId, canRestore }: { templateId: number; canRestore: boolean }) {
  const revisionsQuery = useTemplateRevisions(templateId);
  const restore = useRestoreTemplateRevision();
  const [confirming, setConfirming] = useState<TemplateRevision | null>(null);

  const handleRestore = async () => {
    if (!confirming) return;
    const revision = confirming;
    try {
      await restore.mutateAsync({ templateId, revision: revision.revision });
      toast({ title: `Revision ${revision.revision} restored`, description: "Review the field changes if the fields differ.", duration: 4000 });
    } catch (err) {
      toast({ variant: "destructive", title: "Restore failed", description: err instanceof Error ? err.message : undefined });
    } finally {
      setConfirming(null);
    }
  };

  const revisions = revisionsQuery.data ?? [];

  return (
    <div className="rounded-xl border p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
        <History className="h-4 w-4 text-slate-500" aria-hidden="true" />
        File history
        {revisions.length > 0 && <span className="text-sm font-normal text-slate-500">({revisions.length})</span>}
      </h2>
      <div className="mt-4">
        {revisionsQuery.isPending ? (
          <Skeleton className="h-16 bg-slate-100" aria-label="Loading the file history" />
        ) : revisionsQuery.isError ? (
          <p className="text-sm text-red-600">{revisionsQuery.error.message || "Couldn't load the file history."}</p>
        ) : revisions.length === 0 ? (
          <p className="text-sm text-slate-500">No file history yet.</p>
        ) : (
          <ol className="divide-y divide-slate-100" aria-label="Revisions, newest first">
            {revisions.map((revision) => {
              const changeText = revisionChangeText(revision);
              return (
                <li key={revision.revision} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-0.5">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
                      Revision {revision.revision} · {revisionSourceLabel(revision.source)}
                      {revision.is_current && (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                          Current
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500">
                      <span title={parseServerDate(revision.created_at)?.toLocaleString()}>{relativeTime(revision.created_at)}</span>
                      {" · "}by {revision.created_by_name}
                      {changeText && ` · ${changeText}`}
                    </p>
                    {revision.note && <p className="break-words text-xs text-amber-700">{revision.note}</p>}
                  </div>
                  {canRestore && !revision.is_current && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 shrink-0 self-start px-2 text-xs"
                      disabled={restore.isPending}
                      onClick={() => setConfirming(revision)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                      Restore<span className="sr-only"> revision {revision.revision}</span>
                    </Button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <Dialog open={confirming !== null} onOpenChange={(open) => !open && !restore.isPending && setConfirming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore revision {confirming?.revision}?</DialogTitle>
            <DialogDescription>{confirming ? restoreRevisionConfirmText(confirming) : ""}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirming(null)} disabled={restore.isPending}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void handleRestore()} disabled={restore.isPending}>
              {restore.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              Restore
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
