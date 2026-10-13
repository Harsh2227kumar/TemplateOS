import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";
import type { FieldArrayWithId, FieldErrors, UseFormReturn } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { MonoKey } from "@/components/fields/pipeline-ui";
import { FIELD_TYPE_OPTIONS, VALIDATION_PRESETS, fieldTypeLabel, keyToLabel } from "@/lib/template-pipeline";

import { SOURCE_LABEL, type FieldFormValue, type FieldSetupValues } from "./field-setup-schema";

interface FieldRowCardProps {
  form: UseFormReturn<FieldSetupValues>;
  /** The useFieldArray item (its `id` is the React key; `rowId` the DB id). */
  field: FieldArrayWithId<FieldSetupValues, "fields", "id">;
  index: number;
  /** Live values of this row (titles follow edits). */
  live: Partial<FieldFormValue>;
  isAiStaged: boolean;
  rowErrors: FieldErrors<FieldFormValue> | undefined;
  isCollapsed: boolean;
  isLast: boolean;
  onToggleCollapsed: () => void;
  onMove: (delta: -1 | 1) => void;
  onDelete: () => void;
}

/** One editable field row: summary header (collapse, reorder, delete) and its settings. */
export function FieldRowCard({
  form,
  field,
  index,
  live,
  isAiStaged,
  rowErrors,
  isCollapsed,
  isLast,
  onToggleCollapsed,
  onMove,
  onDelete,
}: FieldRowCardProps) {
  const rowKey = live.field_name ?? "";
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
              onClick={onToggleCollapsed}
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
                onClick={() => onMove(-1)}
                aria-label={`Move field ${index + 1} up`}
              >
                <ChevronUp className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                disabled={isLast}
                onClick={() => onMove(1)}
                aria-label={`Move field ${index + 1} down`}
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-red-600 hover:text-red-700"
                onClick={onDelete}
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
}
