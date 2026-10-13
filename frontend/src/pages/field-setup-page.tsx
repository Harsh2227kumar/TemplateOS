import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useFieldArray, useForm, useWatch, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ChevronsDownUp, ChevronsUpDown, ListTodo, Loader2, Plus, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Form } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/context/auth-context";
import { AiSuggestionsPanel } from "@/components/fields/AiSuggestionsPanel";
import { Notice, PipelineLoadError, PipelineSteps } from "@/components/fields/pipeline-ui";
import { DeleteFieldDialog } from "@/features/field-setup/DeleteFieldDialog";
import { FieldRowCard } from "@/features/field-setup/FieldRowCard";
import {
  FIELD_KEYS,
  blankField,
  fieldSetupSchema,
  seedField,
  toFieldUpsert,
  type FieldFormValue,
  type FieldSetupValues,
} from "@/features/field-setup/field-setup-schema";
import { LockedFieldsView } from "@/features/field-setup/LockedFieldsView";
import { combineQueries, useSaveTemplateFields, useTemplate, useTemplateFields } from "@/hooks/queries";
import { useSeedOnce } from "@/hooks/use-seed-once";
import { ApiError, type FieldSuggestion, type TemplateField } from "@/lib/api";
import { parseRouteId } from "@/lib/route-params";
import { canManageTemplate, isFieldType, pipelineErrorMessage } from "@/lib/template-pipeline";

const byDisplayOrder = (fields: TemplateField[]) => [...fields].sort((a, b) => a.display_order - b.display_order);

export function FieldSetupPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const routeId = parseRouteId(id);
  const templateId = routeId ?? 0;

  const templateQuery = useTemplate(templateId);
  const fieldsQuery = useTemplateFields(templateId);
  const load = combineQueries<ApiError>([templateQuery, fieldsQuery]);
  const saveFields = useSaveTemplateFields(templateId);
  const template = templateQuery.data ?? null;
  const lockedFields = useMemo(() => byDisplayOrder(fieldsQuery.data ?? []), [fieldsQuery.data]);

  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  // Keys accepted from the AI panel but not saved yet (highlight only).
  const [aiStagedKeys, setAiStagedKeys] = useState<string[]>([]);

  const form = useForm<FieldSetupValues>({
    resolver: zodResolver(fieldSetupSchema),
    mode: "onBlur",
    reValidateMode: "onChange",
    defaultValues: { fields: [] },
  });
  const { fields, append, remove, move } = useFieldArray({ control: form.control, name: "fields" });
  const { isSubmitting, isDirty, errors } = form.formState;

  // Fill the form once per template. Later refetches (e.g. after another
  // page invalidated the fields) must not wipe edits in progress.
  const isSeeded = useSeedOnce(templateId, fieldsQuery.data, load.isReady, (data) => {
    form.reset({ fields: byDisplayOrder(data).map(seedField) });
    setCollapsed({});
  });

  // Live values: titles, AI duplicate guard and section suggestions follow edits.
  const watchedFields = useWatch({ control: form.control, name: "fields" }) ?? [];
  const existingKeys = watchedFields
    .map((field) => field?.field_name?.trim())
    .filter((name): name is string => Boolean(name));
  const sectionOptions = useMemo(
    () => [...new Set(watchedFields.map((f) => f?.section?.trim()).filter((s): s is string => Boolean(s)))].sort(),
    [watchedFields],
  );

  // Warn before leaving with unsaved edits.
  useEffect(() => {
    if (!isDirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  const canManage = canManageTemplate(template, user);

  /** Map a 422 Pydantic detail ([{loc: ["body","fields",i,"x"], msg}]) onto rows. */
  const applyServerErrors = (detail: unknown): string[] => {
    const leftovers: string[] = [];
    if (!Array.isArray(detail)) return leftovers;
    for (const item of detail) {
      const loc: unknown[] = Array.isArray(item?.loc) ? item.loc : [];
      const message = typeof item?.msg === "string" ? item.msg.replace(/^Value error, /, "") : "Invalid value";
      const index = loc.findIndex((part) => part === "fields");
      const row = index >= 0 ? loc[index + 1] : undefined;
      const name = index >= 0 ? loc[index + 2] : undefined;
      if (typeof row === "number" && typeof name === "string" && FIELD_KEYS.has(name)) {
        form.setError(`fields.${row}.${name as keyof FieldFormValue}` as const, { message });
        setCollapsed((prev) => ({ ...prev, [fields[row]?.id ?? ""]: false }));
      } else {
        leftovers.push(message);
      }
    }
    return leftovers;
  };

  const onSubmit = async (values: FieldSetupValues) => {
    if (!template || isSubmitting) return;
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const saved = await saveFields.mutateAsync({
        fields: values.fields.map(toFieldUpsert),
        mark_configured: true,
      });
      // Reseed from the response so ids/rows stay in sync with the server.
      form.reset({ fields: saved.map(seedField) });
      setAiStagedKeys([]);
      setSaveSuccess(true);
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status === 422 && Array.isArray(caught.detail)) {
          const leftovers = applyServerErrors(caught.detail);
          setSaveError(
            leftovers.length
              ? `Some values were rejected: ${leftovers.join("; ")}`
              : "Some values were rejected — see the highlighted fields.",
          );
        } else if (caught.status === 409) {
          setSaveError(`Duplicate field key: ${caught.message}`);
        } else {
          setSaveError(pipelineErrorMessage(caught, "edit fields"));
        }
      } else {
        setSaveError("Could not save fields. Please try again.");
      }
    }
  };

  const onInvalid = (formErrors: FieldErrors<FieldSetupValues>) => {
    const rows = Array.isArray(formErrors.fields) ? formErrors.fields : [];
    const bad = rows.map((row, index) => (row ? index : -1)).filter((index) => index >= 0);
    setSaveSuccess(false);
    setSaveError(
      `Fix ${bad.length} field${bad.length === 1 ? "" : "s"} before saving (${bad.map((i) => `#${i + 1}`).join(", ")}).`,
    );
    setCollapsed((prev) => {
      const next = { ...prev };
      for (const index of bad) if (fields[index]) next[fields[index].id] = false;
      return next;
    });
    const firstBad = bad[0];
    if (firstBad !== undefined) {
      window.setTimeout(() => {
        document.getElementById(`field-row-${firstBad}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 50);
    }
  };

  // Accept an AI proposal: stage it as a NEW row (Save all persists it).
  const handleAcceptSuggestion = (suggestion: FieldSuggestion) => {
    append({
      source: "ai",
      field_name: suggestion.field_name,
      field_label: suggestion.field_label ?? "",
      field_type: isFieldType(suggestion.field_type) ? suggestion.field_type : "text",
      is_required: suggestion.is_required,
      ai_enabled: true,
      description: suggestion.reason ?? "",
      example_value: (suggestion.example_value ?? "").slice(0, 255),
      validation_rule: "",
      section: suggestion.section ?? "",
    });
    setAiStagedKeys((keys) => [...keys, suggestion.field_name]);
    setSaveSuccess(false);
  };

  const confirmDelete = () => {
    if (deleteIndex === null) return;
    const removedKey = watchedFields[deleteIndex]?.field_name;
    remove(deleteIndex);
    if (removedKey) setAiStagedKeys((keys) => keys.filter((key) => key !== removedKey));
    setDeleteIndex(null);
    setSaveSuccess(false);
  };

  const moveRow = (from: number, to: number) => {
    if (to < 0 || to >= fields.length) return;
    move(from, to);
    setSaveSuccess(false);
  };

  // ── views ───────────────────────────────────────────────────────────
  if (routeId === null) {
    return <PipelineLoadError status={404} onBack={() => navigate("/templates")} />;
  }

  if (load.error && !isSeeded) {
    return (
      <PipelineLoadError
        status={load.error.status}
        message={load.error.message || "Could not load the field setup page."}
        onBack={() => navigate("/templates")}
        onRetry={load.retry}
      />
    );
  }

  if (!isSeeded || !template) {
    return (
      <div className="max-w-4xl space-y-6 pb-10">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-full max-w-md" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const backToTemplate = () => navigate(`/templates/${template.id}`);

  if (!canManage) {
    return (
      <div className="mx-auto max-w-xl space-y-4 px-2 py-16 text-center">
        <h2 className="text-2xl font-semibold">Only template managers can edit fields</h2>
        <p className="text-sm text-slate-600">
          Field setup configures the form for this template, so it is limited to people who manage it.
        </p>
        <Button variant="outline" onClick={backToTemplate}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
      </div>
    );
  }

  if (template.status === "locked") {
    return <LockedFieldsView fields={lockedFields} onBack={backToTemplate} />;
  }

  const statusBadgeClass =
    template.status === "field_configured"
      ? "border-violet-200 bg-violet-50 text-violet-700"
      : template.status === "active"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-slate-200 bg-slate-50 text-slate-600";

  const allCollapsed = fields.length > 0 && fields.every((f) => collapsed[f.id]);

  const saveButton = (
    <Button type="submit" className="gap-2" disabled={isSubmitting}>
      {isSubmitting ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          Saving…
        </>
      ) : (
        <>
          <Save className="h-4 w-4" />
          Save all
        </>
      )}
    </Button>
  );

  return (
    <div className="max-w-6xl space-y-6 pb-10">
      <div className="space-y-3">
        <Button variant="ghost" onClick={backToTemplate} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={3} />
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold sm:text-3xl">Field Setup</h1>
          <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span>{template.name}</span>
            <Badge variant="outline" className={`capitalize ${statusBadgeClass}`}>
              {template.status.replace(/_/g, " ")}
            </Badge>
            {isDirty && (
              <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
                Unsaved changes
              </Badge>
            )}
          </p>
        </div>
      </div>

      {saveError && <Notice tone="error">{saveError}</Notice>}
      {saveSuccess && !saveError && (
        <Notice tone="success">Fields saved. The template is configured and ready for forms.</Notice>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Form {...form}>
          <form className="min-w-0 space-y-4" onSubmit={form.handleSubmit(onSubmit, onInvalid)} noValidate>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-slate-500">
                Order here is the order of the form. Saving replaces the field set — removed rows are deleted.
              </p>
              <div className="flex flex-wrap gap-2">
                {fields.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => setCollapsed(Object.fromEntries(fields.map((f) => [f.id, !allCollapsed])))}
                  >
                    {allCollapsed ? <ChevronsUpDown className="h-4 w-4" /> : <ChevronsDownUp className="h-4 w-4" />}
                    {allCollapsed ? "Expand all" : "Collapse all"}
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  className="gap-2"
                  onClick={() => {
                    append({ ...blankField(), source: "manual" });
                    setSaveSuccess(false);
                  }}
                >
                  <Plus className="h-4 w-4" />
                  Add field
                </Button>
                {saveButton}
              </div>
            </div>

            <datalist id="field-section-options">
              {sectionOptions.map((section) => (
                <option key={section} value={section} />
              ))}
            </datalist>

            {fields.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                  <ListTodo className="h-10 w-10 text-slate-300" />
                  <p className="max-w-sm text-sm text-slate-600">
                    No fields yet. Clean the template or detect placeholders to create them automatically, or
                    add them by hand.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button type="button" variant="outline" onClick={() => navigate(`/templates/${template.id}/clean`)}>
                      Clean template
                    </Button>
                    <Button type="button" variant="outline" className="gap-2" onClick={() => append(blankField())}>
                      <Plus className="h-4 w-4" />
                      Add first field
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <ol className="space-y-3">
                {fields.map((field, index) => {
                  const live = watchedFields[index] ?? field;
                  const rowErrors = errors.fields?.[index];
                  const isCollapsed = Boolean(collapsed[field.id]) && !rowErrors;
                  return (
                    <FieldRowCard
                      key={field.id}
                      form={form}
                      field={field}
                      index={index}
                      live={live}
                      isAiStaged={aiStagedKeys.includes(live.field_name ?? "")}
                      rowErrors={rowErrors}
                      isCollapsed={isCollapsed}
                      isLast={index === fields.length - 1}
                      onToggleCollapsed={() => setCollapsed((prev) => ({ ...prev, [field.id]: !isCollapsed }))}
                      onMove={(delta) => moveRow(index, index + delta)}
                      onDelete={() => setDeleteIndex(index)}
                    />
                  );
                })}
              </ol>
            )}

            {fields.length > 0 && <div className="flex justify-end border-t pt-4">{saveButton}</div>}
          </form>
        </Form>

        {/* AI Suggestions panel — proposals only; accepted rows are saved by Save all. */}
        <aside id="ai-suggestions" className="min-w-0 lg:sticky lg:top-6">
          <AiSuggestionsPanel templateId={templateId} existingKeys={existingKeys} onAccept={handleAcceptSuggestion} />
        </aside>
      </div>

      <DeleteFieldDialog
        open={deleteIndex !== null}
        field={deleteIndex !== null ? watchedFields[deleteIndex] ?? null : null}
        onCancel={() => setDeleteIndex(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
