import { useEffect, useMemo, useRef, useState } from "react";
import { FormProvider, useForm, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { AlertCircle, CheckCircle, ChevronLeft, Loader2, RefreshCw, RotateCcw, Save } from "lucide-react";

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
  type Document,
  type DocumentFormValues,
  type TemplateField,
  type TemplateResponse,
} from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import { buildFormSchema } from "@/lib/validation";

/** Re-renders every 30s so relative times ("2 minutes ago") stay current. */
function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

function latestTimestamp(times: Array<string | null | undefined>): string | null {
  let best: string | null = null;
  for (const t of times) {
    if (!t || Number.isNaN(new Date(t).getTime())) continue;
    if (best === null || new Date(t) > new Date(best)) best = t;
  }
  return best;
}

export function EditDocumentPage() {
  const navigate = useNavigate();
  const { id: documentIdParam } = useParams<{ id: string }>();
  const documentId = documentIdParam ? parseInt(documentIdParam, 10) : 0;

  const [template, setTemplate] = useState<TemplateResponse | null>(null);
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [document, setDocument] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // "not_found" covers 404/403 on the document; anything else is a retryable load error.
  const [loadError, setLoadError] = useState<{ kind: "not_found" | "error"; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  // Form values as of the last load or successful save, used by "Reset Form".
  const lastSavedValuesRef = useRef<DocumentFormValues>({});
  const formRef = useRef<HTMLFormElement>(null);
  const savedTimerRef = useRef<number | null>(null);
  useNow();

  const token = getAccessToken();

  useEffect(() => {
    if (!documentId) {
      navigate("/", { replace: true });
      return;
    }
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      setLoadError(null);
      setSaveError(null);
      setDocument(null);
      setTemplate(null);
      let doc: Document;
      try {
        doc = await documentsApi.getDocument(token, documentId);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load document:", err);
        if (err instanceof ApiError && (err.status === 404 || err.status === 403)) {
          setLoadError({ kind: "not_found", message: err.message });
        } else {
          setLoadError({
            kind: "error",
            message: err instanceof Error && err.message ? err.message : "Failed to load document. Please try again.",
          });
        }
        setLoading(false);
        return;
      }
      try {
        const [templateData, fieldsData] = await Promise.all([
          templatesApi.getTemplateDetail(token, doc.template_id),
          templatesApi.getFields(token, doc.template_id),
        ]);
        if (cancelled) return;
        setFields(fieldsData);
        setTemplate(templateData);
        setDocument(doc);
        setLastSavedAt(latestTimestamp([doc.updated_at, ...(doc.values ?? []).map((v) => v.updated_at)]));
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load template for document:", err);
        setLoadError({
          kind: "error",
          message:
            err instanceof Error && err.message
              ? err.message
              : "Failed to load the document's template. Please try again.",
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, [documentId, token, reloadKey, navigate]);

  useEffect(
    () => () => {
      if (savedTimerRef.current !== null) window.clearTimeout(savedTimerRef.current);
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

  // Prefill from the saved values; fields without one fall back to their default.
  useEffect(() => {
    if (fields.length > 0 && document) {
      const initial = buildInitialValues(fields, document.values ?? []);
      lastSavedValuesRef.current = structuredClone(initial);
      form.reset(initial);
    }
  }, [fields, document, form]);

  useUnsavedChangesWarning(isDirty);
  useSaveShortcut(() => formRef.current?.requestSubmit(), !loading && !saving && !!document);

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

  const handleUpdateDraft = async (formData: DocumentFormValues) => {
    if (!documentId || saving) return;

    setSaving(true);
    setSaveError(null);

    try {
      const saved = await documentsApi.saveValues(token, documentId, {
        values: serializeValues(fields, formData),
      });

      // The saved values become the new baseline for isDirty and Reset Form.
      const normalized = normalizeSavedFormValues(fields, formData);
      lastSavedValuesRef.current = structuredClone(normalized);
      form.reset(normalized);
      setLastSavedAt(
        latestTimestamp((saved?.values ?? []).map((v) => v.updated_at)) ?? new Date().toISOString(),
      );

      setJustSaved(true);
      if (savedTimerRef.current !== null) window.clearTimeout(savedTimerRef.current);
      savedTimerRef.current = window.setTimeout(() => setJustSaved(false), 2000);
      toast({ title: "Draft saved", duration: 2500 });
    } catch (err) {
      const split =
        err instanceof ApiError && err.status === 422
          ? splitValidationErrors(err.detail, fields.map((f) => f.field_name))
          : null;
      if (split) {
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
        setSaveError(err instanceof Error && err.message ? err.message : "Failed to update draft. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (isDirty && !window.confirm("Discard your unsaved changes and go back to the last saved version?")) return;
    form.reset(structuredClone(lastSavedValuesRef.current));
    setSaveError(null);
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
        <h2 className="text-xl font-semibold text-slate-900">Couldn't load this draft</h2>
        <p className="mt-2 text-slate-500">{loadError.message}</p>
        <div className="mt-6 flex justify-center gap-3">
          <Button onClick={() => setReloadKey((k) => k + 1)}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
          <Button asChild variant="outline">
            <Link to="/">Go to Dashboard</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (!document || !template) {
    return (
      <div className="mx-auto max-w-3xl py-12 text-center">
        <AlertCircle className="mx-auto mb-4 h-12 w-12 text-slate-400" />
        <h2 className="text-xl font-semibold text-slate-900">Document not found</h2>
        <p className="mt-2 text-slate-500">
          The draft you're looking for doesn't exist or you don't have access to it.
        </p>
        <Button asChild className="mt-6">
          <Link to="/">Go to Dashboard</Link>
        </Button>
      </div>
    );
  }

  const savedDate = lastSavedAt ? new Date(lastSavedAt) : null;
  const savedLabel =
    savedDate && !Number.isNaN(savedDate.getTime())
      ? formatDistanceToNow(savedDate, { addSuffix: true })
      : "unknown";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="space-y-2">
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
      </div>

      {saveError && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
          <p className="break-words text-red-800">{saveError}</p>
        </div>
      )}

      <FormProvider {...form}>
        <form
          ref={formRef}
          onSubmit={form.handleSubmit(handleUpdateDraft, handleInvalid)}
          noValidate
          className="space-y-6"
        >
          <Card>
            <CardHeader className="space-y-3">
              <div>
                <CardTitle>Edit draft</CardTitle>
                <CardDescription className="mt-1.5">
                  Make changes and save to update your draft. Required fields are marked with{" "}
                  <span className="text-red-500">*</span>.
                </CardDescription>
              </div>
              <FormProgress fields={fields} />
            </CardHeader>
            <CardContent>
              <fieldset disabled={saving} className="min-w-0">
                <DocumentFormSections
                  fields={fields}
                  aiContext={{ templateId: document.template_id, documentId: document.id }}
                  disabled={saving}
                />
              </fieldset>
            </CardContent>
            <CardFooter className="sticky bottom-0 z-10 flex flex-col-reverse gap-2 rounded-b-lg border-t bg-slate-50/95 py-3 backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:gap-3">
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
                <Button type="submit" disabled={saving} className="w-full sm:w-auto">
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
            </CardFooter>
          </Card>
        </form>
      </FormProvider>
    </div>
  );
}
