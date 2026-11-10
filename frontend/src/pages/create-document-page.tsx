import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCircle, ChevronLeft, Loader2, Save } from "lucide-react";

import { buildInitialValues, normalizeSavedFormValues, serializeValues } from "@/components/forms/form-values";
import { useSaveShortcut, useUnsavedChangesWarning } from "@/components/forms/use-form-guards";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { DraftFormShell } from "@/features/documents/DraftFormShell";
import { DraftLoadError, DraftLoadingSkeleton, DraftNotFound } from "@/features/documents/DraftLoadStates";
import { useDraftForm } from "@/features/documents/use-draft-form";
import {
  combineQueries,
  useCreateDocument,
  useSaveDocumentValues,
  useTemplate,
  useTemplateFields,
} from "@/hooks/queries";
import { useSeedOnce } from "@/hooks/use-seed-once";
import type { ApiError, DocumentFormValues, TemplateField } from "@/lib/api";
import { parseRouteId } from "@/lib/route-params";

export function CreateDocumentPage() {
  const navigate = useNavigate();
  const { id: templateIdParam } = useParams<{ id: string }>();
  const templateId = parseRouteId(templateIdParam) ?? 0;

  const templateQuery = useTemplate(templateId);
  const fieldsQuery = useTemplateFields(templateId);
  const load = combineQueries<ApiError>([templateQuery, fieldsQuery]);
  const template = templateQuery.data ?? null;
  const createDocument = useCreateDocument();
  const saveValues = useSaveDocumentValues();

  // Fields as of seeding: the schema and inputs never change under the user.
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Id of a document created by an earlier submit whose value save failed.
  // Retries reuse it instead of creating a duplicate document.
  const createdDocIdRef = useRef<number | null>(null);
  const redirectTimerRef = useRef<number | null>(null);
  const { form, formRef, handleInvalid, describeSaveError, requestSubmit } = useDraftForm(fields);
  const { isDirty } = form.formState;

  const isSeeded = useSeedOnce(templateId, fieldsQuery.data, load.isReady, (data) => {
    setFields(data);
    if (data.length > 0) form.reset(buildInitialValues(data));
  });

  useEffect(() => {
    if (!templateId) navigate("/templates", { replace: true });
  }, [templateId, navigate]);

  useEffect(
    () => () => {
      if (redirectTimerRef.current !== null) window.clearTimeout(redirectTimerRef.current);
    },
    [],
  );

  useUnsavedChangesWarning(isDirty && !saveSuccess);
  useSaveShortcut(requestSubmit, isSeeded && !saving && !saveSuccess);

  const handleSaveDraft = async (formData: DocumentFormValues) => {
    if (!templateId || saving || saveSuccess) return;

    setSaving(true);
    setSaveError(null);

    try {
      // Step 1: create the document (skipped on retry if it already exists).
      let docId = createdDocIdRef.current;
      if (docId === null) {
        const doc = await createDocument.mutateAsync({ template_id: templateId });
        docId = doc.id;
        createdDocIdRef.current = docId;
      }

      // Step 2: save values (lists as JSON arrays, blank items dropped).
      await saveValues.mutateAsync({ documentId: docId, body: { values: serializeValues(fields, formData) } });

      // Mark the form clean so the unsaved-changes guard lets the redirect through.
      form.reset(normalizeSavedFormValues(fields, formData));
      setSaveSuccess(true);
      toast({ title: "Draft saved", description: "Opening it in the editor…", duration: 2500 });
      const savedId = docId;
      redirectTimerRef.current = window.setTimeout(() => {
        navigate(`/documents/${savedId}/edit`, { replace: true });
      }, 1200);
    } catch (err) {
      setSaveError(describeSaveError(err, "Failed to save draft. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const goBack = () => {
    // navigate(-1) would leave the app when the page was opened directly.
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate(templateId ? `/templates/${templateId}` : "/templates");
  };

  const loadError = isSeeded ? null : load.error;
  const notFound = loadError && (loadError.status === 404 || loadError.status === 403);

  if (loadError && !notFound) {
    return (
      <DraftLoadError
        title="Couldn't load this template"
        message={loadError.message || "Failed to load template. Please try again."}
        onRetry={load.retry}
        backTo="/templates"
        backLabel="Browse Templates"
      />
    );
  }

  if (!loadError && !isSeeded) return <DraftLoadingSkeleton />;

  if (!template || notFound) {
    return (
      <DraftNotFound
        title="Template not found"
        description="The template you're looking for doesn't exist or you don't have access to it."
        backTo="/templates"
        backLabel="Browse Templates"
      />
    );
  }

  const busy = saving || saveSuccess;

  return (
    <DraftFormShell
      form={form}
      formRef={formRef}
      onSubmit={form.handleSubmit(handleSaveDraft, handleInvalid)}
      fields={fields}
      aiContext={{ templateId, documentId: createdDocIdRef.current }}
      disabled={busy}
      saveError={saveError}
      title="Fill in the form"
      description={
        <>
          Required fields are marked with <span className="text-red-500">*</span>.
        </>
      }
      header={
        <>
          <Button variant="ghost" size="sm" onClick={goBack} className="-ml-2 h-8 px-2 text-slate-600">
            <ChevronLeft className="mr-1 h-4 w-4" />
            Back
          </Button>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h1 className="break-words text-2xl font-bold text-slate-900">{template.name}</h1>
              <p className="mt-1 text-sm text-slate-500">{template.description || "No description"}</p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                {template.category}
              </span>
              <span
                className={`rounded px-2 py-1 text-xs font-medium ${
                  template.status === "draft"
                    ? "bg-yellow-100 text-yellow-700"
                    : template.status === "active"
                      ? "bg-green-100 text-green-700"
                      : "bg-blue-100 text-blue-700"
                }`}
              >
                {template.status.replace("_", " ")}
              </span>
            </div>
          </div>
        </>
      }
      notice={
        saveSuccess && (
          <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-4" role="status">
            <CheckCircle className="h-5 w-5 shrink-0 text-green-600" />
            <div>
              <p className="font-medium text-green-800">Draft saved successfully!</p>
              <p className="text-sm text-green-700">Opening the editor…</p>
            </div>
          </div>
        )
      }
      footerClassName="sm:justify-end"
      footer={
        <>
          <span className="hidden text-xs text-slate-400 sm:mr-auto sm:inline">
            {isDirty ? "Unsaved changes · " : ""}Ctrl+S to save
          </span>
          <Button type="button" variant="outline" onClick={goBack} disabled={saving} className="w-full sm:w-auto">
            Cancel
          </Button>
          <Button type="submit" disabled={busy} className="w-full sm:w-auto">
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : saveSuccess ? (
              <>
                <CheckCircle className="mr-2 h-4 w-4" />
                Saved!
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Draft
              </>
            )}
          </Button>
        </>
      }
    />
  );
}
