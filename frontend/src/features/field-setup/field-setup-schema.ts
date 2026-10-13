import * as z from "zod";

import type { TemplateField, TemplateFieldUpsert } from "@/lib/api";
import {
  FIELD_TYPE_VALUES,
  KEY_PATTERN,
  KEY_RULE_MESSAGE,
  VALIDATION_RULE_MESSAGE,
  isFieldType,
  isValidValidationRule,
  normalizeValidationRule,
  type FieldTypeValue,
} from "@/lib/template-pipeline";

export const SOURCE_LABEL: Record<string, string> = {
  detected: "Detected",
  cleaned: "From cleaning",
  manual: "Manual",
  ai: "AI",
};

// Form value for one field row. `rowId` carries the DB id for existing
// fields (useFieldArray injects its own `id`); undefined means "new field".
export interface FieldFormValue {
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

export const fieldSetupSchema = z.object({
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

export type FieldSetupValues = z.infer<typeof fieldSetupSchema>;

export function seedField(field: TemplateField): FieldFormValue {
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

export function blankField(): FieldFormValue {
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

export const FIELD_KEYS = new Set([
  "field_name", "field_label", "field_type", "is_required", "ai_enabled",
  "description", "example_value", "validation_rule", "section",
]);

/** Form row -> PUT /templates/{id}/fields item (blank optional values omitted). */
export function toFieldUpsert(field: FieldFormValue): TemplateFieldUpsert {
  return {
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
  };
}
