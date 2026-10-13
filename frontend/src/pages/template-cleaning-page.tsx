import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Notice, PipelineLoadError, PipelineSteps } from "@/components/fields/pipeline-ui";
import { useAuth } from "@/context/auth-context";
import { ApplyBar, ApplyCleaningDialog, CleanPreviewDialog } from "@/features/template-cleaning/ApplyCleaning";
import { CleaningResultView } from "@/features/template-cleaning/CleaningResultView";
import { ManualPlaceholdersPanel } from "@/features/template-cleaning/ManualPlaceholdersPanel";
import { SuggestionsPanel } from "@/features/template-cleaning/SuggestionsPanel";
import { useCleaningSession } from "@/features/template-cleaning/use-cleaning-session";
import {
  combineQueries,
  useCleanSuggestions,
  useCleanTemplate,
  usePreviewClean,
  useTemplate,
  useTemplateContent,
} from "@/hooks/queries";
import { useSeedOnce } from "@/hooks/use-seed-once";
import type { ApiError, CleanResponse } from "@/lib/api";
import { parseRouteId } from "@/lib/route-params";
import { canManageTemplate, pipelineErrorMessage } from "@/lib/template-pipeline";

export function TemplateCleaningPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const routeId = parseRouteId(id);
  const templateId = routeId ?? 0;

  const templateQuery = useTemplate(templateId);
  const contentQuery = useTemplateContent(templateId);
  const load = combineQueries<ApiError>([templateQuery, contentQuery]);
  const template = templateQuery.data ?? null;
  const content = contentQuery.data ?? null;
  const canManage = canManageTemplate(template, user);

  // Suggestions are snapshotted into the session on first load and on Re-scan,
  // so a background refetch never resets the user's choices.
  const session = useCleaningSession();
  const suggestionsQuery = useCleanSuggestions(templateId, Boolean(template) && canManage);
  useSeedOnce(templateId, suggestionsQuery.data, !suggestionsQuery.isFetching, session.loadSuggestions);
  const suggestionsLoading = suggestionsQuery.isFetching;
  const suggestionsError =
    suggestionsQuery.isError && !suggestionsQuery.isFetching
      ? pipelineErrorMessage(suggestionsQuery.error as ApiError, "clean this template")
      : null;
  const rescan = async () => {
    const latest = await suggestionsQuery.refetch();
    if (latest.isSuccess) session.loadSuggestions(latest.data);
  };

  const previewClean = usePreviewClean(templateId);
  const cleanTemplate = useCleanTemplate(templateId);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [applyOpen, setApplyOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<CleanResponse | null>(null);
  const previewLoading = previewClean.isPending;
  const isApplying = cleanTemplate.isPending;
  const { blockingProblem } = session;

  const runPreview = async () => {
    if (blockingProblem || previewLoading) return;
    setPreviewOpen(true);
    setPreviewError(null);
    try {
      session.setPreview(await previewClean.mutateAsync({ replacements: session.buildPayload(), confirm: false }));
    } catch (err: any) {
      setPreviewError(pipelineErrorMessage(err, "clean this template"));
    }
  };

  const applyCleaning = async () => {
    if (isApplying || blockingProblem) return;
    setActionError(null);
    try {
      const response = await cleanTemplate.mutateAsync({ replacements: session.buildPayload(), confirm: true });
      setApplyOpen(false);
      setResult(response);
      window.scrollTo({ top: 0 });
    } catch (err: any) {
      setApplyOpen(false);
      setActionError(pipelineErrorMessage(err, "clean this template"));
    }
  };

  // ── views ─────────────────────────────────────────────────────────
  if (routeId === null) {
    return <PipelineLoadError status={404} onBack={() => navigate("/templates")} />;
  }

  if (load.isLoading) {
    return (
      <div className="max-w-6xl space-y-6">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-5 w-full max-w-md" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-96 w-full rounded-2xl" />
          <Skeleton className="h-96 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  if (load.error || !template || !content) {
    return (
      <PipelineLoadError
        status={load.error?.status}
        message={load.error?.message || "Failed to load template"}
        onBack={() => navigate("/templates")}
        onRetry={load.retry}
      />
    );
  }

  const backToTemplate = () => navigate(`/templates/${template.id}`);

  if (!canManage) {
    return (
      <div className="mx-auto max-w-xl space-y-4 px-2 py-16 text-center">
        <h2 className="text-2xl font-semibold">Only template managers can clean this template</h2>
        <p className="text-sm text-slate-600">
          Cleaning turns sample text into placeholders, so it is limited to people who manage
          this template.
        </p>
        <Button variant="outline" onClick={backToTemplate}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
      </div>
    );
  }

  if (result) {
    return (
      <CleaningResultView
        templateName={template.name}
        result={result}
        onBack={backToTemplate}
        onReviewPlaceholders={() => navigate(`/templates/${template.id}/placeholders`)}
        onFieldSetup={() => navigate(`/templates/${template.id}/fields`)}
        // The clean mutation invalidated the template and its content, which
        // are already being refetched in the background.
        onCleanAgain={() => {
          setResult(null);
          session.setPreview(null);
        }}
      />
    );
  }

  return (
    <div className="max-w-7xl space-y-6 pb-4">
      <div className="space-y-3">
        <Button variant="ghost" onClick={backToTemplate} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={1} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold sm:text-3xl">Template Cleaning</h1>
            <p className="mt-2 text-sm text-slate-600">
              {template.name} · Turn sample values and blanks into{" "}
              <span className="font-mono text-xs">{"{{ placeholders }}"}</span>. Your original file is
              never modified.
            </p>
          </div>
          {content.has_processed && (
            <Badge variant="outline" className="w-fit shrink-0 bg-blue-50 text-blue-700">
              A cleaned copy exists — applying replaces it
            </Badge>
          )}
        </div>
      </div>

      {actionError && (
        <Notice tone="error" title="Cleaning failed">
          {actionError}
        </Notice>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <SuggestionsPanel
          session={session}
          loading={suggestionsLoading}
          error={suggestionsError}
          onRescan={() => void rescan()}
        />
        <ManualPlaceholdersPanel content={content} session={session} />
      </div>

      <ApplyBar
        session={session}
        previewLoading={previewLoading}
        isApplying={isApplying}
        onPreview={() => void runPreview()}
        onApply={() => setApplyOpen(true)}
      />

      <CleanPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        preview={session.preview}
        loading={previewLoading}
        error={previewError}
        canApply={!blockingProblem}
        onApply={() => {
          setPreviewOpen(false);
          setApplyOpen(true);
        }}
      />

      <ApplyCleaningDialog
        open={applyOpen}
        onOpenChange={setApplyOpen}
        session={session}
        hasProcessed={content.has_processed}
        isApplying={isApplying}
        onConfirm={() => void applyCleaning()}
      />
    </div>
  );
}
