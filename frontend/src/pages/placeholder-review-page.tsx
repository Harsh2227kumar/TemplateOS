import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Braces, Eraser, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { Notice, PipelineLoadError, PipelineSteps } from "@/components/fields/pipeline-ui";
import { DetectPlaceholdersCard } from "@/features/placeholder-review/DetectPlaceholdersCard";
import { DetectedFieldsList } from "@/features/placeholder-review/DetectedFieldsList";
import { InvalidPlaceholdersCard } from "@/features/placeholder-review/InvalidPlaceholdersCard";
import { RebuildFieldsDialog } from "@/features/placeholder-review/RebuildFieldsDialog";
import { usePlaceholderReview } from "@/features/placeholder-review/use-placeholder-review";
import { parseRouteId } from "@/lib/route-params";

export function PlaceholderReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const templateId = parseRouteId(id);
  const review = usePlaceholderReview(templateId ?? 0);
  const { load, template, fields, sortedFields, detection, canManage, busy } = review;

  if (templateId === null) {
    return <PipelineLoadError status={404} onBack={() => navigate("/templates")} />;
  }

  if (load.isLoading) {
    return (
      <div className="max-w-4xl space-y-6">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-5 w-full max-w-sm" />
        <Skeleton className="h-72 w-full rounded-2xl" />
      </div>
    );
  }

  if (load.error || !template) {
    return (
      <PipelineLoadError
        status={load.error?.status}
        message={load.error?.message || "Failed to load template"}
        onBack={() => navigate("/templates")}
        onRetry={load.retry}
      />
    );
  }

  const invalid = detection?.warnings.invalid_names ?? [];
  const hasRunDetection = detection !== null || template.status !== "uploaded";
  const scanning = busy === "detect" || busy === "rebuild";
  const hasProcessed = Boolean(template.processed_file_path);
  const fieldNames = new Set(fields.map((f) => f.field_name));
  const staleCount = detection?.stale_fields?.length ?? 0;
  const goTo = (step: "clean" | "fields") => navigate(`/templates/${template.id}/${step}`);

  return (
    <div className="max-w-4xl space-y-6 pb-10">
      <div className="space-y-3">
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={2} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold sm:text-3xl">Placeholder Review</h1>
            <p className="mt-2 text-sm text-slate-600">
              {template.name} · {fields.length} field{fields.length === 1 ? "" : "s"}
              {detection
                ? ` · scanned the ${detection.source_file === "processed" ? "cleaned copy" : "original file"}`
                : ""}
            </p>
          </div>
          {canManage && hasRunDetection && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="gap-2" disabled={!!busy} onClick={() => review.runDetection(false)}>
                <RefreshCw className={`h-4 w-4 ${busy === "detect" ? "animate-spin" : ""}`} />
                Scan again
              </Button>
              {fields.length > 0 && (
                <Button
                  variant="ghost"
                  className="text-slate-600"
                  disabled={!!busy}
                  onClick={() => review.setRebuildOpen(true)}
                >
                  Rebuild fields
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {review.actionError && <Notice tone="error">{review.actionError}</Notice>}
      {review.actionMessage && !review.actionError && <Notice tone="success">{review.actionMessage}</Notice>}
      {scanning && (
        <Notice tone="info">
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Scanning the document for placeholders…
          </span>
        </Notice>
      )}

      {detection?.warnings.parse_error && (
        <Notice tone="error" title="This template cannot be generated yet">
          Some placeholders have invalid names, so the document engine cannot read the template. Fix the
          names below.
        </Notice>
      )}

      {invalid.length > 0 && (
        <InvalidPlaceholdersCard
          invalid={invalid}
          fixKeys={review.fixKeys}
          onFixKeyChange={review.setFixKey}
          onFix={review.fixInvalid}
          fieldNames={fieldNames}
          canManage={canManage}
          busy={busy}
        />
      )}

      {sortedFields.length > 0 ? (
        <DetectedFieldsList fields={sortedFields} detection={detection} />
      ) : hasRunDetection && !scanning ? (
        <EmptyState
          icon={Braces}
          title="No placeholders yet"
          description={
            hasProcessed
              ? "The cleaned copy has no valid {{placeholders}}. Clean the template again to add some."
              : "This document has no {{placeholders}}. Template Cleaning finds the blanks, labels and sample values for you."
          }
          actionLabel="Clean this template"
          onAction={canManage ? () => goTo("clean") : undefined}
        />
      ) : (
        !scanning && (
          <DetectPlaceholdersCard
            canManage={canManage}
            hasProcessed={hasProcessed}
            busy={!!busy}
            onDetect={() => review.runDetection(false)}
            onClean={() => goTo("clean")}
          />
        )
      )}

      {staleCount > 0 && (
        <Notice
          tone="warning"
          title="Fields without a placeholder"
          action={
            canManage ? (
              <Button size="sm" variant="outline" onClick={() => goTo("fields")}>
                Review in Field Setup
              </Button>
            ) : undefined
          }
        >
          {staleCount} field{staleCount === 1 ? " is" : "s are"} not used by the document. They will be ignored
          when generating — remove them if they are not needed.
        </Notice>
      )}

      <div className="flex flex-wrap gap-3 border-t pt-6">
        {fields.length > 0 && (
          <Button className="gap-2" onClick={() => goTo("fields")}>
            Continue to Field Setup
            <ArrowRight className="h-4 w-4" />
          </Button>
        )}
        {canManage && (
          <Button variant={fields.length > 0 ? "outline" : "default"} className="gap-2" onClick={() => goTo("clean")}>
            <Eraser className="h-4 w-4" />
            Clean template
          </Button>
        )}
      </div>

      <RebuildFieldsDialog
        open={review.rebuildOpen}
        onOpenChange={review.setRebuildOpen}
        fieldCount={fields.length}
        busy={busy}
        onConfirm={() => review.runDetection(true)}
      />
    </div>
  );
}
