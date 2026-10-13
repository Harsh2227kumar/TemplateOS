import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle, ChevronLeft, Loader2, RotateCcw, Save } from "lucide-react";

import { buildInitialValues, normalizeSavedFormValues, serializeValues } from "@/components/forms/form-values";
import { useSaveShortcut, useUnsavedChangesWarning } from "@/components/forms/use-form-guards";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { DraftFormShell } from "@/features/documents/DraftFormShell";
import { DraftLoadError, DraftLoadingSkeleton, DraftNotFound } from "@/features/documents/DraftLoadStates";
import { latestTimestamp } from "@/features/documents/draft-timestamps";
import { GenerationPanel } from "@/features/documents/GenerationPanel";
import type { DownloadFormat } from "@/features/documents/generation";
import { useDraftForm, useNow } from "@/features/documents/use-draft-form";
import {
  combineQueries,
  useDocument,
  useDownloadGenerated,
  useGenerateDocument,
  useRetryPdf,
  useSaveDocumentValues,
  useTemplate,
  useTemplateFields,
} from "@/hooks/queries";
import { useSeedOnce } from "@/hooks/use-seed-once";
import type { ApiError, DocumentFormValues, GeneratedInfo, TemplateField } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";
import { parseRouteId } from "@/lib/route-params";

export function EditDocumentPage() {
  const navigate = useNavigate();
  const { id: documentIdParam } = useParams<{ id: string }>();
  const documentId = parseRouteId(documentIdParam) ?? 0;

  // The draft first; its template and fields once the template id is known.
  const documentQuery = useDocument(documentId);
  const document = documentQuery.data ?? null;
  const templateId = document?.template_id ?? 0;
  const templateQuery = useTemplate(templateId);
  const fieldsQuery = useTemplateFields(templateId);
  const load = combineQueries<ApiError>([documentQuery, templateQuery, fieldsQuery]);
  const template = templateQuery.data ?? null;
  const saveValues = useSaveDocumentValues();
  const generateDocument = useGenerateDocument();
  const retryPdf = useRetryPdf();
  const downloadGenerated = useDownloadGenerated();
  // The latest generate / retry result; null falls back to the draft's own
  // `generated` (refetched after each generate, retry and save).
  const [latestGenerated, setLatestGenerated] = useState<GeneratedInfo | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<DownloadFormat | null>(null);

  // Fields as of seeding: the schema and inputs never change under the user.
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  // Form values as of the last load or successful save, used by "Reset Form".
  const lastSavedValuesRef = useRef<DocumentFormValues>({});
  const savedTimerRef = useRef<number | null>(null);
  const { form, formRef, handleInvalid, describeSaveError, requestSubmit } = useDraftForm(fields);
  const { isDirty } = form.formState;
  useNow();

  // Prefill once per draft from the saved values; fields without one fall
  // back to their default. Refetches after a save never reset the form.
  const seedData = useMemo(
    () => (document && fieldsQuery.data ? { document, fields: fieldsQuery.data } : undefined),
    [document, fieldsQuery.data],
  );
  const isSeeded = useSeedOnce(documentId, seedData, load.isReady, (data) => {
    setFields(data.fields);
    setSaveError(null);
    setLastSavedAt(
      latestTimestamp([data.document.updated_at, ...(data.document.values ?? []).map((v) => v.updated_at)]),
    );
    if (data.fields.length > 0) {
      const initial = buildInitialValues(data.fields, data.document.values ?? []);
      lastSavedValuesRef.current = structuredClone(initial);
      form.reset(initial);
    }
  });

  useEffect(() => {
    if (!documentId) navigate("/", { replace: true });
  }, [documentId, navigate]);

  useEffect(
    () => () => {
      if (savedTimerRef.current !== null) window.clearTimeout(savedTimerRef.current);
    },
    [],
  );

  useUnsavedChangesWarning(isDirty);
  useSaveShortcut(requestSubmit, isSeeded && !saving && !generateDocument.isPending);

  /** Save the form; true on success. */
  const saveDraft = async (formData: DocumentFormValues): Promise<boolean> => {
    if (!documentId || saving) return false;

    setSaving(true);
    setSaveError(null);

    try {
      const saved = await saveValues.mutateAsync({
        documentId,
        body: { values: serializeValues(fields, formData) },
      });

      // The saved values become the new baseline for isDirty and Reset Form.
      const normalized = normalizeSavedFormValues(fields, formData);
      lastSavedValuesRef.current = structuredClone(normalized);
      form.reset(normalized);
      setLastSavedAt(latestTimestamp((saved?.values ?? []).map((v) => v.updated_at)) ?? new Date().toISOString());

      setJustSaved(true);
      if (savedTimerRef.current !== null) window.clearTimeout(savedTimerRef.current);
      savedTimerRef.current = window.setTimeout(() => setJustSaved(false), 2000);
      toast({ title: "Draft saved", duration: 2500 });
      // The refetched draft now carries the server's "values changed" flag.
      setLatestGenerated(null);
      return true;
    } catch (err) {
      setSaveError(describeSaveError(err, "Failed to update draft. Please try again."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateDraft = async (formData: DocumentFormValues) => {
    await saveDraft(formData);
  };

  const runGenerate = async () => {
    setGenerateError(null);
    try {
      const result = await generateDocument.mutateAsync(documentId);
      setLatestGenerated(result);
      toast({
        title: "Document generated",
        description:
          result.pdf_status === "ok"
            ? "DOCX and PDF are ready to download."
            : result.pdf_status === "failed"
              ? "The DOCX is ready; the PDF conversion failed."
              : "The DOCX is ready to download.",
        duration: 3500,
      });
    } catch (err) {
      // 422 with field errors maps onto the inputs like a failed save.
      setGenerateError(
        describeSaveError(err, "Failed to generate the document. Please try again.") ??
          "Some fields need attention. Fix the highlighted fields, then generate again.",
      );
    }
  };

  /** Generation uses the SAVED values, so unsaved edits are saved first. */
  const handleGenerate = () => {
    if (saving || generateDocument.isPending) return;
    if (!isDirty) {
      void runGenerate();
      return;
    }
    void form.handleSubmit(async (formData) => {
      if (await saveDraft(formData)) await runGenerate();
    }, handleInvalid)();
  };

  const handleRetryPdf = async () => {
    try {
      const result = await retryPdf.mutateAsync(documentId);
      setLatestGenerated(result);
      toast(
        result.pdf_status === "ok"
          ? { title: "PDF ready", duration: 2500 }
          : { variant: "destructive", title: "PDF still unavailable", description: result.pdf_error ?? undefined },
      );
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Couldn't retry the PDF",
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const handleDownload = async (format: DownloadFormat) => {
    setDownloading(format);
    try {
      await downloadGenerated.mutateAsync({ documentId, format, name: document?.name });
    } catch (err) {
      const status = (err as ApiError | undefined)?.status;
      toast({
        variant: "destructive",
        title: status === 409 && format === "pdf" ? "PDF not available" : "Download failed",
        description: err instanceof Error ? err.message : undefined,
      });
      // The server state may differ from what we show (e.g. file removed).
      if (status === 404 || status === 409) void documentQuery.refetch();
    } finally {
      setDownloading(null);
    }
  };

  const handleReset = () => {
    if (isDirty && !window.confirm("Discard your unsaved changes and go back to the last saved version?")) return;
    form.reset(structuredClone(lastSavedValuesRef.current));
    setSaveError(null);
  };

  // "Not found" covers 404/403 on the draft; anything else is a retryable load error.
  const loadError = isSeeded ? null : load.error;
  const notFound =
    loadError && loadError === documentQuery.error && (loadError.status === 404 || loadError.status === 403);

  if (loadError && !notFound) {
    return (
      <DraftLoadError
        title="Couldn't load this draft"
        message={
          loadError.message ||
          (loadError === documentQuery.error
            ? "Failed to load document. Please try again."
            : "Failed to load the document's template. Please try again.")
        }
        onRetry={load.retry}
        backTo="/"
        backLabel="Go to Dashboard"
      />
    );
  }

  if (!loadError && !isSeeded) return <DraftLoadingSkeleton />;

  if (!document || !template || notFound) {
    return (
      <DraftNotFound
        title="Document not found"
        description="The draft you're looking for doesn't exist or you don't have access to it."
        backTo="/"
        backLabel="Go to Dashboard"
      />
    );
  }

  const savedDate = parseServerDate(lastSavedAt);
  const savedLabel = savedDate ? formatDistanceToNow(savedDate, { addSuffix: true }) : "unknown";

  return (
    <DraftFormShell
      form={form}
      formRef={formRef}
      onSubmit={form.handleSubmit(handleUpdateDraft, handleInvalid)}
      fields={fields}
      aiContext={{ templateId: document.template_id, documentId: document.id }}
      disabled={saving || generateDocument.isPending}
      saveError={saveError}
      notice={
        <GenerationPanel
          generated={latestGenerated ?? document.generated ?? null}
          isDirty={isDirty}
          generating={generateDocument.isPending}
          retryingPdf={retryPdf.isPending}
          downloading={downloading}
          disabled={saving}
          error={generateError}
          onGenerate={handleGenerate}
          onRetryPdf={() => void handleRetryPdf()}
          onDownload={(format) => void handleDownload(format)}
        />
      }
      title="Edit draft"
      description={
        <>
          Make changes and save to update your draft. Required fields are marked with{" "}
          <span className="text-red-500">*</span>.
        </>
      }
      header={
        <>
          <Button variant="ghost" size="sm" onClick={() => navigate("/")} className="-ml-2 h-8 px-2 text-slate-600">
            <ChevronLeft className="mr-1 h-4 w-4" />
            Dashboard
          </Button>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h1 className="break-words text-2xl font-bold text-slate-900">
                {document.name || `Draft ${document.id}`}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                Template: {template.name} ·{" "}
                <span title={savedDate ? savedDate.toLocaleString() : undefined}>Last saved {savedLabel}</span>
                {isDirty && <span className="ml-1 font-medium text-amber-700">· Unsaved changes</span>}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                {template.category}
              </span>
              <span
                className={`rounded px-2 py-1 text-xs font-medium ${
                  document.status === "draft"
                    ? "bg-yellow-100 text-yellow-700"
                    : document.status === "active"
                      ? "bg-green-100 text-green-700"
                      : "bg-blue-100 text-blue-700"
                }`}
              >
                {document.status.replace("_", " ")}
              </span>
            </div>
          </div>
        </>
      }
      footerClassName="sm:justify-between"
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/")}
            disabled={saving}
            className="w-full sm:w-auto"
          >
            Back to Dashboard
          </Button>
          <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-3">
            <span className="hidden text-xs text-slate-400 lg:inline">Ctrl+S to save</span>
            <Button
              type="button"
              variant="outline"
              onClick={handleReset}
              disabled={saving || !isDirty}
              className="w-full sm:w-auto"
              title="Restore the last saved values"
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Reset Form
            </Button>
            <Button type="submit" disabled={saving || generateDocument.isPending} className="w-full sm:w-auto">
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving…
                </>
              ) : justSaved && !isDirty ? (
                <>
                  <CheckCircle className="mr-2 h-4 w-4" />
                  Saved
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Update Draft
                </>
              )}
            </Button>
          </div>
        </>
      }
    />
  );
}
