import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ChevronLeft, Eraser, FilePenLine, FileText, ListChecks, Loader2, RotateCcw, ScanSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { DraftLoadError, DraftNotFound } from "@/features/documents/DraftLoadStates";
import { fieldChangesSummary } from "@/features/word-editor/editor-review-model";
import { useTemplate } from "@/hooks/queries";
import { useFieldChanges, useRestoreTemplateRevision, useTemplateRevisions } from "@/hooks/queries/word-editor-actions";
import { parseRouteId } from "@/lib/route-params";

const USABLE_STATUSES = ["field_configured", "active"];

/**
 * V1.7 P2.1: after a template file edit, what it means for the form (new
 * placeholders, removed fields, blanks), routed into the existing pipeline.
 */
export function TemplateFieldChangesPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const templateId = parseRouteId(id) ?? 0;
  const changesQuery = useFieldChanges(templateId);
  const template = useTemplate(templateId).data ?? null;
  const revisions = useTemplateRevisions(templateId).data ?? [];
  const restore = useRestoreTemplateRevision();
  const [restoring, setRestoring] = useState(false);

  if (!templateId) {
    return <DraftNotFound title="Template not found" description="This link is not valid." backTo="/templates" backLabel="Back to Library" />;
  }
  if (changesQuery.isPending) {
    return (
      <div className="mx-auto max-w-3xl space-y-4" aria-busy="true" aria-label="Loading the field changes">
        <Skeleton className="h-8 w-2/3 bg-slate-100" />
        <Skeleton className="h-40 bg-slate-100" />
      </div>
    );
  }
  if (changesQuery.isError) {
    const status = changesQuery.error.status;
    if (status === 404 || status === 403) {
      return (
        <DraftNotFound
          title="Template not found"
          description="This template doesn't exist or you can't review it."
          backTo="/templates"
          backLabel="Back to Library"
        />
      );
    }
    return (
      <DraftLoadError
        title="Couldn't check the field changes"
        message={changesQuery.error.message || "Please try again."}
        onRetry={() => void changesQuery.refetch()}
        backTo={`/templates/${templateId}`}
        backLabel="Template"
      />
    );
  }

  const changes = changesQuery.data;
  const summary = fieldChangesSummary(changes);
  // The newest revision before the one under review (newest first from the API).
  const previous = revisions.find((revision) => revision.revision < changes.revision) ?? null;
  const base = `/templates/${templateId}`;

  const handleRestorePrevious = async () => {
    if (!previous || restoring) return;
    setRestoring(true);
    try {
      await restore.mutateAsync({ templateId, revision: previous.revision });
      toast({ title: `Revision ${previous.revision} restored`, duration: 3000 });
      navigate(base);
    } catch (err) {
      toast({ variant: "destructive", title: "Restore failed", description: err instanceof Error ? err.message : undefined });
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <Button variant="ghost" size="sm" asChild className="-ml-2 h-8 px-2 text-slate-600">
          <Link to={base}>
            <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
            Template
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold text-slate-900">Field changes</h1>
        <p className="text-sm text-slate-500">
          {template?.name ?? "Template"} · revision {changes.revision}
        </p>
      </div>

      {summary.kind === "render_error" ? (
        <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
          <p className="flex items-start gap-2 font-medium text-red-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {summary.title}
          </p>
          <p className="break-words text-sm text-red-800">{summary.lines[0]}</p>
          <p className="text-sm text-red-800">Documents keep using the previous file until this is fixed.</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link to={`${base}/edit-file`}>
                <FilePenLine className="h-4 w-4" aria-hidden="true" />
                Open the editor again
              </Link>
            </Button>
            {previous && (
              <Button type="button" size="sm" variant="outline" className="bg-white" onClick={() => void handleRestorePrevious()} disabled={restoring}>
                {restoring ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RotateCcw className="h-4 w-4" aria-hidden="true" />}
                Restore revision {previous.revision}
              </Button>
            )}
          </div>
        </div>
      ) : summary.kind === "none" ? (
        <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4" role="status">
          <p className="flex items-center gap-2 font-medium text-emerald-800">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {summary.title}
          </p>
          <div className="flex flex-wrap gap-2">
            {template && USABLE_STATUSES.includes(template.status) && (
              <Button asChild size="sm">
                <Link to={`/documents/create/${templateId}`}>
                  <FileText className="h-4 w-4" aria-hidden="true" />
                  Create a draft
                </Link>
              </Button>
            )}
            <Button asChild size="sm" variant="outline" className="bg-white">
              <Link to={base}>Back to the template</Link>
            </Button>
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="space-y-5 p-5">
            <div className="space-y-1" role="status">
              <h2 className="font-semibold text-slate-900">{summary.title}</h2>
              <ul className="list-inside list-disc text-sm text-slate-600">
                {summary.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>

            {changes.added.length > 0 && (
              <section className="space-y-2" aria-label="New fields">
                <h3 className="text-sm font-semibold text-slate-800">New in the file</h3>
                <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
                  {changes.added.map((item) => (
                    <li key={item.key} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                      <span className="text-slate-900">{item.suggested_label}</span>
                      <span className="flex items-center gap-2 text-xs text-slate-500">
                        <span className="font-mono">{item.key}</span>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 capitalize">{item.suggested_type}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {changes.removed.length > 0 && (
              <section className="space-y-2" aria-label="Removed fields">
                <h3 className="text-sm font-semibold text-slate-800">No longer in the file</h3>
                <p className="text-xs text-slate-500">Remove these fields on the fields page, or put them back in the file.</p>
                <ul className="flex flex-wrap gap-1.5">
                  {changes.removed.map((name) => (
                    <li key={name} className="rounded-full bg-amber-50 px-2 py-0.5 font-mono text-xs text-amber-800">
                      {name}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
              {summary.cleanFirst && (
                <Button asChild size="sm">
                  <Link to={`${base}/clean`}>
                    <Eraser className="h-4 w-4" aria-hidden="true" />
                    Turn blanks into fields
                  </Link>
                </Button>
              )}
              {summary.detectNew && (
                <Button asChild size="sm" variant={summary.cleanFirst ? "outline" : "default"}>
                  <Link to={`${base}/placeholders`}>
                    <ScanSearch className="h-4 w-4" aria-hidden="true" />
                    Detect the new fields
                  </Link>
                </Button>
              )}
              {summary.reviewFields && (
                <Button asChild size="sm" variant="outline">
                  <Link to={`${base}/fields`}>
                    <ListChecks className="h-4 w-4" aria-hidden="true" />
                    Review fields
                  </Link>
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
