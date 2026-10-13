import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useFieldArray, useForm, useWatch, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  ChevronsDownUp,
  ChevronsUpDown,
  ListTodo,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { useAuth } from "@/context/auth-context";
import { AiSuggestionsPanel } from "@/components/fields/AiSuggestionsPanel";
import { MonoKey, Notice, PipelineLoadError, PipelineSteps } from "@/components/fields/pipeline-ui";
import { ApiError, templatesApi, type FieldSuggestion, type TemplateField } from "@/lib/api";
import {
  FIELD_TYPE_OPTIONS,
  FIELD_TYPE_VALUES,
  KEY_PATTERN,
  KEY_RULE_MESSAGE,
  VALIDATION_PRESETS,
  VALIDATION_RULE_MESSAGE,
  canManageTemplate,
  fieldTypeLabel,
  isFieldType,
  isValidValidationRule,
  keyToLabel,
  normalizeValidationRule,
  pipelineErrorMessage,
  type FieldTypeValue,
  type ManagedTemplate,
} from "@/lib/template-pipeline";

const SOURCE_LABEL: Record<string, string> = {
  detected: "Detected",
  cleaned: "From cleaning",
  manual: "Manual",
  ai: "AI",
};

// Form value for one field row. `rowId` carries the DB id for existing
// fields (useFieldArray injects its own `id`); undefined means "new field".
interface FieldFormValue {
  rowId?: number;
  source?: string;
  field_name: string;
  field_label: string;
  field_type: FieldTypeValue;
  is_required: boolean;
  ai_enabled: boolean;
  description: string;
  example_value: string;
  validation_rule: string;
  section: string;
}

const fieldRowSchema = z.object({
  rowId: z.number().optional(),
  source: z.string().optional(),
  field_name: z
    .string()
    .trim()
    .min(1, "Field key is required")
    .max(100, "Field key must be 100 characters or fewer")
    .regex(KEY_PATTERN, KEY_RULE_MESSAGE),
  field_label: z.string().max(150, "Label must be 150 characters or fewer"),
  field_type: z.enum(FIELD_TYPE_VALUES, {
    errorMap: () => ({ message: "Please select a field type" }),
  }),
  is_required: z.boolean(),
  ai_enabled: z.boolean(),
  description: z.string().max(2000, "Help text must be 2000 characters or fewer"),
  example_value: z.string().max(255, "Example must be 255 characters or fewer"),
  validation_rule: z
    .string()
    .max(255, "Validation rule must be 255 characters or fewer")
    .refine(isValidValidationRule, VALIDATION_RULE_MESSAGE),
  section: z.string().max(100, "Section must be 100 characters or fewer"),
});

const fieldSetupSchema = z.object({
  fields: z.array(fieldRowSchema).superRefine((fields, ctx) => {
    const seen = new Map<string, number>();
    for (const [index, field] of fields.entries()) {
      const key = field.field_name.trim();
      if (!key) continue;
      if (seen.has(key)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [index, "field_name"],
          message: `Duplicate key — field ${seen.get(key)! + 1} already uses “${key}”`,
        });
      } else {
        seen.set(key, index);
      }
    }
  }),
});

type FieldSetupValues = z.infer<typeof fieldSetupSchema>;

function seedField(field: TemplateField): FieldFormValue {
  return {
    rowId: field.id,
    source: field.source,
    field_name: field.field_name,
    field_label: field.field_label ?? "",
    field_type: isFieldType(field.field_type) ? field.field_type : "text",
    is_required: field.is_required,
    ai_enabled: field.ai_enabled,
    description: field.description ?? "",
    example_value: field.example_value ?? "",
    validation_rule: field.validation_rule ?? "",
    section: field.section ?? "",
  };
}

function blankField(): FieldFormValue {
  return {
    field_name: "",
    field_label: "",
    field_type: "text",
    is_required: true,
    ai_enabled: false,
    description: "",
    example_value: "",
    validation_rule: "",
    section: "",
  };
}

const FIELD_KEYS = new Set([
  "field_name", "field_label", "field_type", "is_required", "ai_enabled",
  "description", "example_value", "validation_rule", "section",
]);

export function FieldSetupPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const templateId = Number(id);

  const [template, setTemplate] = useState<ManagedTemplate | null>(null);
  const [lockedFields, setLockedFields] = useState<TemplateField[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ message: string; status?: number } | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const form = useForm<FieldSetupValues>({
    resolver: zodResolver(fieldSetupSchema),
    mode: "onBlur",
    reValidateMode: "onChange",
    defaultValues: { fields: [] },
  });

  const { fields, append, remove, move } = useFieldArray({ control: form.control, name: "fields" });
  const { isSubmitting, isDirty, errors } = form.formState;

  // Live values: titles, AI duplicate guard and section suggestions follow edits.
  const watchedFields = useWatch({ control: form.control, name: "fields" }) ?? [];
  const existingKeys = watchedFields
    .map((field) => field?.field_name?.trim())
    .filter((name): name is string => Boolean(name));
  const sectionOptions = useMemo(
    () =>
      [...new Set(watchedFields.map((f) => f?.section?.trim()).filter((s): s is string => Boolean(s)))].sort(),
    [watchedFields],
  );

  // Keys accepted from the AI panel but not saved yet (highlight only).
  const [aiStagedKeys, setAiStagedKeys] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const [templateData, fieldData] = await Promise.all([
          templatesApi.getTemplateDetail(templateId),
          templatesApi.getFields(templateId),
        ]);
        if (!active) return;
        const ordered = [...fieldData].sort((a, b) => a.display_order - b.display_order);
        setTemplate(templateData);
        setLockedFields(ordered);
        form.reset({ fields: ordered.map(seedField) });
        setCollapsed({});
      } catch (caught) {
        if (!active) return;
        setLoadError(
          caught instanceof ApiError
            ? { message: caught.message, status: caught.status }
            : { message: "Could not load the field setup page." },
        );
      } finally {
        if (active) setIsLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
    // form is stable for the lifetime of the page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId, reloadToken]);

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
  const isLocked = template?.status === "locked";

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
      const saved = await templatesApi.saveFields(templateId, {
        fields: values.fields.map((field) => ({
          id: field.rowId,
          field_name: field.field_name.trim(),
          field_label: field.field_label.trim() || undefined,
          field_type: field.field_type,
          is_required: field.is_required,
          description: field.description.trim() || undefined,
          example_value: field.example_value.trim() || undefined,
          validation_rule: normalizeValidationRule(field.validation_rule) || undefined,
          section: field.section.trim() || undefined,
          ai_enabled: field.ai_enabled,
        })),
        mark_configured: true,
      });
      // Reseed from the response so ids/rows stay in sync with the server.
      form.reset({ fields: saved.map(seedField) });
      setLockedFields(saved);
      setAiStagedKeys([]);
      if (saved.length > 0 && template.status !== "active" && template.status !== "field_configured") {
        setTemplate({ ...template, status: "field_configured" });
      }
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
  if (isLoading) {
    return (
      <div className="max-w-4xl space-y-6 pb-10">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-full max-w-md" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (loadError || !template) {
    return (
      <PipelineLoadError
        status={loadError?.status}
        message={loadError?.message}
        onBack={() => navigate("/templates")}
        onRetry={() => setReloadToken((n) => n + 1)}
      />
    );
  }

  if (!canManage) {
    return (
      <div className="mx-auto max-w-xl space-y-4 px-2 py-16 text-center">
        <h2 className="text-2xl font-semibold">Only template managers can edit fields</h2>
        <p className="text-sm text-slate-600">
          Field setup configures the form for this template, so it is limited to people who manage it.
        </p>
        <Button variant="outline" onClick={() => navigate(`/templates/${template.id}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
      </div>
    );
  }

  const statusBadgeClass =
    template.status === "field_configured"
      ? "border-violet-200 bg-violet-50 text-violet-700"
      : template.status === "active"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-slate-200 bg-slate-50 text-slate-600";

  if (isLocked) {
    return (
      <div className="max-w-4xl space-y-6 pb-10">
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <h1 className="text-2xl font-semibold sm:text-3xl">Field Setup</h1>
        <Notice tone="warning">This template is locked. Field settings are read-only.</Notice>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListTodo className="h-5 w-5" />
              Fields
            </CardTitle>
            <CardDescription>{lockedFields.length} field(s), in display order.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <ol className="divide-y divide-slate-100">
              {lockedFields.map((field, index) => (
                <li key={field.id} className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-6">
                  <span className="text-sm font-medium text-slate-400">{index + 1}.</span>
                  <span className="text-sm font-medium text-slate-900">{field.field_label || field.field_name}</span>
                  <MonoKey name={field.field_name} />
                  <Badge variant="outline" className="bg-slate-50">{fieldTypeLabel(field.field_type)}</Badge>
                  {field.is_required && (
                    <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">required</Badge>
                  )}
                  {field.ai_enabled && (
                    <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">AI</Badge>
                  )}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    );
  }

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
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
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
                    onClick={() =>
                      setCollapsed(Object.fromEntries(fields.map((f) => [f.id, !allCollapsed])))
                    }
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
                  const rowKey = live.field_name ?? "";
                  const isAiStaged = aiStagedKeys.includes(rowKey);
                  const rowErrors = errors.fields?.[index];
                  const isCollapsed = Boolean(collapsed[field.id]) && !rowErrors;
                  const source = live.source ?? field.source;
                  return (
                    <li key={field.id} id={`field-row-${index}`}>
                      <Card
                        className={
                          rowErrors
                            ? "border-red-300"
                            : isAiStaged
                              ? "border-indigo-200 ring-1 ring-indigo-100"
                              : undefined
                        }
                      >
                        <CardHeader className="space-y-0 p-4">
                          <div className="flex items-start justify-between gap-2">
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left"
                              onClick={() => setCollapsed((prev) => ({ ...prev, [field.id]: !isCollapsed }))}
                              aria-expanded={!isCollapsed}
                            >
                              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">
                                {index + 1}
                              </span>
                              <span className="min-w-0 break-words font-medium text-slate-800">
                                {live.field_label?.trim() || (rowKey ? keyToLabel(rowKey) : "New field")}
                              </span>
                              <MonoKey name={rowKey} />
                              <Badge variant="outline" className="bg-slate-50">
                                {fieldTypeLabel(live.field_type ?? "text")}
                              </Badge>
                              {live.section?.trim() && <Badge variant="outline">{live.section}</Badge>}
                              {!live.is_required && (
                                <Badge variant="outline" className="text-slate-500">optional</Badge>
                              )}
                              {source && SOURCE_LABEL[source] && (
                                <span className="text-xs text-slate-400">{SOURCE_LABEL[source]}</span>
                              )}
                              {!field.rowId && (
                                <Badge variant="outline" className="border-indigo-200 bg-indigo-50 text-indigo-700">
                                  {isAiStaged ? "AI suggestion" : "New"}
                                </Badge>
                              )}
                              {rowErrors && (
                                <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">
                                  needs attention
                                </Badge>
                              )}
                            </button>
                            <div className="flex shrink-0 items-center">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                disabled={index === 0}
                                onClick={() => moveRow(index, index - 1)}
                                aria-label={`Move field ${index + 1} up`}
                              >
                                <ChevronUp className="h-4 w-4" />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                disabled={index === fields.length - 1}
                                onClick={() => moveRow(index, index + 1)}
                                aria-label={`Move field ${index + 1} down`}
                              >
                                <ChevronDown className="h-4 w-4" />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-red-600 hover:text-red-700"
                                onClick={() => setDeleteIndex(index)}
                                aria-label={`Delete field ${index + 1}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        </CardHeader>
                        {!isCollapsed && (
                          <CardContent className="space-y-4 px-4 pb-4 pt-0">
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                              <FormField
                                control={form.control}
                                name={`fields.${index}.field_name`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>
                                      Field key <span className="text-red-500">*</span>
                                    </FormLabel>
                                    <FormControl>
                                      <Input
                                        placeholder="e.g. meeting_date"
                                        className="font-mono"
                                        maxLength={100}
                                        autoCapitalize="off"
                                        spellCheck={false}
                                        {...input}
                                      />
                                    </FormControl>
                                    {field.rowId && input.value !== field.field_name && (
                                      <p className="text-xs text-amber-700">
                                        Renaming a key does not change the document — the placeholder must match.
                                      </p>
                                    )}
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.field_label`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>Label</FormLabel>
                                    <FormControl>
                                      <Input
                                        placeholder={rowKey ? keyToLabel(rowKey) : "e.g. Meeting Date"}
                                        maxLength={150}
                                        {...input}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.field_type`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>
                                      Type <span className="text-red-500">*</span>
                                    </FormLabel>
                                    <Select onValueChange={input.onChange} value={input.value}>
                                      <FormControl>
                                        <SelectTrigger>
                                          <SelectValue placeholder="Select a type" />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent className="bg-white text-slate-900">
                                        {FIELD_TYPE_OPTIONS.map((opt) => (
                                          <SelectItem key={opt.value} value={opt.value}>
                                            {opt.label}
                                          </SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.section`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>Section</FormLabel>
                                    <FormControl>
                                      <Input
                                        placeholder="e.g. Meeting Details"
                                        maxLength={100}
                                        list="field-section-options"
                                        {...input}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.example_value`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>Example</FormLabel>
                                    <FormControl>
                                      <Input placeholder="Shown as a hint in the form" maxLength={255} {...input} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.validation_rule`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <FormLabel>Validation</FormLabel>
                                    <div className="flex gap-2">
                                      <FormControl>
                                        <Input
                                          placeholder="e.g. email or min:2|max:50"
                                          maxLength={255}
                                          className="min-w-0 font-mono text-sm"
                                          {...input}
                                        />
                                      </FormControl>
                                      <Select
                                        value=""
                                        onValueChange={(value) =>
                                          form.setValue(
                                            `fields.${index}.validation_rule`,
                                            value === "none" ? "" : value,
                                            { shouldDirty: true, shouldValidate: true },
                                          )
                                        }
                                      >
                                        <SelectTrigger className="w-[110px] shrink-0" aria-label="Validation presets">
                                          <SelectValue placeholder="Presets" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-white text-slate-900">
                                          {VALIDATION_PRESETS.map((preset) => (
                                            <SelectItem key={preset.label} value={preset.value || "none"}>
                                              {preset.label}
                                            </SelectItem>
                                          ))}
                                        </SelectContent>
                                      </Select>
                                    </div>
                                    <p className="text-xs text-slate-500">
                                      min/max count characters, numbers or list items depending on the type.
                                    </p>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>

                            <FormField
                              control={form.control}
                              name={`fields.${index}.description`}
                              render={({ field: input }) => (
                                <FormItem>
                                  <FormLabel>Help text</FormLabel>
                                  <FormControl>
                                    <Textarea
                                      placeholder="Shown under the field in the form…"
                                      className="resize-y"
                                      rows={2}
                                      {...input}
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-2">
                              <FormField
                                control={form.control}
                                name={`fields.${index}.is_required`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <div className="flex items-center gap-3">
                                      <FormControl>
                                        <Switch checked={input.value} onCheckedChange={input.onChange} />
                                      </FormControl>
                                      <FormLabel className="!mt-0">Required</FormLabel>
                                    </div>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name={`fields.${index}.ai_enabled`}
                                render={({ field: input }) => (
                                  <FormItem>
                                    <div className="flex items-center gap-3">
                                      <FormControl>
                                        <Switch checked={input.value} onCheckedChange={input.onChange} />
                                      </FormControl>
                                      <FormLabel className="!mt-0">AI-enabled</FormLabel>
                                    </div>
                                    <p className="text-xs text-slate-500">
                                      Turn on for descriptive fields (agenda, summary); off for facts (dates, amounts).
                                    </p>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          </CardContent>
                        )}
                      </Card>
                    </li>
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

      <Dialog open={deleteIndex !== null} onOpenChange={(open) => !open && setDeleteIndex(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete field?</DialogTitle>
            <DialogDescription>
              {deleteIndex !== null && watchedFields[deleteIndex] && (
                <>
                  “
                  {watchedFields[deleteIndex].field_label?.trim() ||
                    watchedFields[deleteIndex].field_name ||
                    "New field"}
                  ” is removed now and deleted from the template when you save.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteIndex(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              <Trash2 className="mr-2 h-4 w-4" />
              Remove field
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
