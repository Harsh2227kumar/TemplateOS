import * as z from "zod";

import type { CleanSuggestionsResponse, DocSegment, PlaceholderReplacement } from "@/lib/api";
import { FIELD_TYPE_VALUES, KEY_PATTERN, KEY_RULE_MESSAGE, type FieldTypeValue } from "@/lib/template-pipeline";

export const LOCATION_ORDER: DocSegment["location"][] = ["body", "table", "textbox", "header", "footer"];
export const LOCATION_LABEL: Record<DocSegment["location"], string> = {
  body: "Body",
  table: "Tables",
  textbox: "Text boxes",
  header: "Header",
  footer: "Footer",
};
/** Longest text the user may select and convert manually. */
export const MAX_SELECTION = 255;

export const convertSchema = z.object({
  placeholder_key: z
    .string()
    .trim()
    .min(1, "Placeholder key is required")
    .max(100, "Placeholder key must be 100 characters or fewer")
    .regex(KEY_PATTERN, KEY_RULE_MESSAGE),
  field_label: z.string().max(150, "Label must be 150 characters or fewer").optional(),
  field_type: z.enum(FIELD_TYPE_VALUES),
  section: z.string().max(100, "Section must be 100 characters or fewer").optional(),
});
export type ConvertValues = z.infer<typeof convertSchema>;

export type DecisionStatus = "pending" | "accepted" | "rejected";

/** The user's choice for one automatic suggestion (key/label/type may be edited). */
export interface Decision {
  status: DecisionStatus;
  key: string;
  label: string;
  type: FieldTypeValue;
}

/** A placeholder created by selecting text in the document. */
export interface ManualReplacement extends PlaceholderReplacement {
  id: string;
}

/** Every suggestion starts pending, with the server's key, label and type. */
export function seedDecisions(data: CleanSuggestionsResponse): Record<string, Decision> {
  return Object.fromEntries(
    data.suggestions.map((s) => [
      s.id,
      {
        status: "pending" as DecisionStatus,
        key: s.placeholder_key,
        label: s.field_label,
        type: FIELD_TYPE_VALUES.includes(s.field_type as FieldTypeValue) ? (s.field_type as FieldTypeValue) : "text",
      },
    ]),
  );
}
