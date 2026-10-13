import { useEffect, useMemo, useRef, useState } from "react";
import { FormProvider, useForm, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, CheckCircle, ChevronLeft, Loader2, RefreshCw, Save } from "lucide-react";

import { DocumentFormSections, FormProgress, focusFirstError } from "@/components/forms/DocumentFormSections";
import { buildInitialValues, normalizeSavedFormValues, serializeValues } from "@/components/forms/form-values";
import { useSaveShortcut, useUnsavedChangesWarning } from "@/components/forms/use-form-guards";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  documentsApi,
  splitValidationErrors,
  templatesApi,
  type DocumentFormValues,
  type TemplateResponse,
  type TemplateField,
} from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import { buildFormSchema } from "@/lib/validation";

export function CreateDocumentPage() {
  const navigate = useNavigate();
  const { id: templateIdParam } = useParams<{ id: string }>();
  const templateId = templateIdParam ? parseInt(templateIdParam, 10) : 0;

  const [template, setTemplate] = useState<TemplateResponse | null>(null);
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ kind: "not_found" | "error"; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Id of a document created by an earlier submit whose value save failed.
  // Retries reuse it instead of creating a duplicate document.
  const createdDocIdRef = useRef<number | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const redirectTimerRef = useRef<number | null>(null);

  const token = getAccessToken();

  useEffect(() => {
    if (!templateId) {
      navigate("/templates", { replace: true });
      return;
    }
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      setLoadError(null);
      try {
        const [templateData, fieldsData] = await Promise.all([
          templatesApi.getTemplateDetail(token, templateId),
          templatesApi.getFields(token, templateId),
        ]);
        if (cancelled) return;
        setTemplate(templateData);
        setFields(fieldsData);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load template:", err);
        if (err instanceof ApiError && (err.status === 404 || err.status === 403)) {
          setLoadError({ kind: "not_found", message: err.message });
        } else {
          setLoadError({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load template. Please try again.",
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, [templateId, token, reloadKey, navigate]);

  useEffect(
    () => () => {
      if (redirectTimerRef.current !== null) window.clearTimeout(redirectTimerRef.current);
    },
    [],
  );

  const schema = useMemo(() => buildFormSchema(fields), [fields]);
  const form = useForm<DocumentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {},
    mode: "onTouched",
    shouldFocusError: false,
  });
  const { isDirty } = form.formState;

  useEffect(() => {
    if (fields.length > 0) form.reset(buildInitialValues(fields));
  }, [fields, form]);

  useUnsavedChangesWarning(isDirty && !saveSuccess);
  useSaveShortcut(() => formRef.current?.requestSubmit(), !loading && !saving && !saveSuccess);

  const handleInvalid = (errors: FieldErrors<DocumentFormValues>) => {
    const count = Object.keys(errors).length;
    focusFirstError(fields, errors);
    toast({
      variant: "destructive",
      title: count === 1 ? "1 field needs attention" : `${count} fields need attention`,
      description: "Fix the highlighted fields, then save again.",
      duration: 4000,
    });
  };

  const handleSaveDraft = async (formData: DocumentFormValues) => {
    if (!templateId || saving || saveSuccess) return;

    setSaving(true);
    setSaveError(null);

    try {
      // Step 1: create the document (skipped on retry if it already exists).
      let docId = createdDocIdRef.current;
      if (docId === null) {
        const doc = await documentsApi.createDocument(token, { template_id: templateId });
        docId = doc.id;
        createdDocIdRef.current = docId;
      }

      // Step 2: save values (lists as JSON arrays, blank items dropped).
      await documentsApi.saveValues(token, docId, { values: serializeValues(fields, formData) });

      // Mark the form clean so the unsaved-changes guard lets the redirect through.
      form.reset(normalizeSavedFormValues(fields, formData));
      setSaveSuccess(true);
      toast({ title: "Draft saved", description: "Opening it in the editor…", duration: 2500 });
      const savedId = docId;
      redirectTimerRef.current = window.setTimeout(() => {
        navigate(`/documents/${savedId}/edit`, { replace: true });
      }, 1200);
    } catch (err) {
      const split =
        err instanceof ApiError && err.status === 422
          ? splitValidationErrors(err.detail, fields.map((f) => f.field_name))
          : null;
      if (split) {
        // Field-specific validation errors from the backend, shown inline.
        Object.entries(split.fieldErrors).forEach(([fieldName, message]) => {
          form.setError(fieldName, { message, type: "server" });
        });
        focusFirstError(fields, form.formState.errors);
        if (split.otherMessages.length > 0) {
          setSaveError(`Validation failed: ${split.otherMessages.join("; ")}`);
        } else if (Object.keys(split.fieldErrors).length === 0) {
          setSaveError((err as Error).message || "Validation failed. Please check the form.");
        }
      } else {
        setSaveError(err instanceof Error && err.message ? err.message : "Failed to save draft. Please try again.");
      }
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

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6" aria-busy="true">
        <div className="h-8 animate-pulse rounded bg-slate-100" />
        <div className="h-64 animate-pulse rounded bg-slate-100" />
      </div>
    );
  }

  if (loadError?.kind === "error") {
    return (
      <div className="mx-auto max-w-3xl py-12 text-center">
        <AlertCircle className="mx-auto mb-4 h-12 w-12 text-red-400" />
        <h2 className="text-xl font-semibold text-slate-900">Couldn't load this template</h2>
        <p className="mt-2 text-slate-500">{loadError.message}</p>
        <div className="mt-6 flex justify-center gap-3">
          <Button onClick={() => setReloadKey((k) => k + 1)}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
          <Button asChild variant="outline">
            <Link to="/templates">Browse Templates</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (!template) {
    return (
      <div className="mx-auto max-w-3xl py-12 text-center">
        <AlertCircle className="mx-auto mb-4 h-12 w-12 text-slate-400" />
        <h2 className="text-xl font-semibold text-slate-900">Template not found</h2>
        <p className="mt-2 text-slate-500">
          The template you're looking for doesn't exist or you don't have access to it.
        </p>
        <Button asChild className="mt-6">
          <Link to="/templates">Browse Templates</Link>
        </Button>
      </div>
    );
  }

  const busy = saving || saveSuccess;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="space-y-2">
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
      </div>

      {saveSuccess && (
        <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-4" role="status">
          <CheckCircle className="h-5 w-5 shrink-0 text-green-600" />
          <div>
            <p className="font-medium text-green-800">Draft saved successfully!</p>
            <p className="text-sm text-green-700">Opening the editor…</p>
          </div>
        </div>
      )}

      {saveError && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
          <p className="break-words text-red-800">{saveError}</p>
        </div>
      )}

      <FormProvider {...form}>
        <form
          ref={formRef}
          onSubmit={form.handleSubmit(handleSaveDraft, handleInvalid)}
          noValidate
          className="space-y-6"
        >
          <Card>
            <CardHeader className="space-y-3">
              <div>
                <CardTitle>Fill in the form</CardTitle>
                <CardDescription className="mt-1.5">
                  Required fields are marked with <span className="text-red-500">*</span>.
                </CardDescription>
              </div>
              <FormProgress fields={fields} />
            </CardHeader>
            <CardContent>
              <fieldset disabled={busy} className="min-w-0">
                <DocumentFormSections
                  fields={fields}
                  aiContext={{ templateId, documentId: createdDocIdRef.current }}
                  disabled={busy}
                />
              </fieldset>
            </CardContent>
            <CardFooter className="sticky bottom-0 z-10 flex flex-col-reverse gap-2 rounded-b-lg border-t bg-slate-50/95 py-3 backdrop-blur sm:flex-row sm:items-center sm:justify-end sm:gap-3">
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
            </CardFooter>
          </Card>
        </form>
      </FormProvider>
    </div>
  );
}
