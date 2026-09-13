import { z } from "zod";

/**
 * Parses validation_rule string and applies appropriate Zod validators.
 *
 * Supported rules:
 * - "email" → z.string().email()
 * - "min:N" → z.string().min(N) or z.number().min(N)
 * - "max:N" → z.string().max(N) or z.number().max(N)
 * - "min:5|max:100" → chained validators
 *
 * Phase 1: regex rules are ignored (server-side only in Phase 2)
 */
export function applyValidationRule(
  schema: z.ZodString | z.ZodNumber | z.ZodArray<any>,
  validationRule: string | null,
  fieldLabel: string
): z.ZodString | z.ZodNumber | z.ZodArray<any> {
  if (!validationRule) return schema;

  const rules = validationRule.split("|").map((r) => r.trim());

  for (const rule of rules) {
    if (rule === "email") {
      if (schema instanceof z.ZodString) {
        schema = schema.email(`${fieldLabel} must be a valid email address`);
      }
    } else if (rule.startsWith("min:")) {
      const minValue = parseInt(rule.split(":")[1], 10);
      if (isNaN(minValue)) continue;

      if (schema instanceof z.ZodString) {
        schema = schema.min(minValue, `${fieldLabel} must be at least ${minValue} characters`);
      } else if (schema instanceof z.ZodNumber) {
        schema = schema.min(minValue, `${fieldLabel} must be at least ${minValue}`);
      } else if (schema instanceof z.ZodArray) {
        schema = schema.min(minValue, `${fieldLabel} must have at least ${minValue} items`);
      }
    } else if (rule.startsWith("max:")) {
      const maxValue = parseInt(rule.split(":")[1], 10);
      if (isNaN(maxValue)) continue;

      if (schema instanceof z.ZodString) {
        schema = schema.max(maxValue, `${fieldLabel} must be at most ${maxValue} characters`);
      } else if (schema instanceof z.ZodNumber) {
        schema = schema.max(maxValue, `${fieldLabel} must be at most ${maxValue}`);
      } else if (schema instanceof z.ZodArray) {
        schema = schema.max(maxValue, `${fieldLabel} must have at most ${maxValue} items`);
      }
    }
    // regex rules are ignored (server-side only in Phase 2)
  }

  return schema;
}
