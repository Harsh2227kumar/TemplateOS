/**
 * AI fill assistant (V1.7 P2.2): the rules for putting the AI's proposals
 * into the draft form.
 *
 * - A field's ORIGIN is derived from its value and the AI flags, never
 *   tracked by events: blank -> "empty"; an "ai_fill" flag whose fingerprint
 *   still matches the value -> "ai"; anything else -> "user". So typing in a
 *   field, or choosing a per-field AI style, makes it the user's.
 * - A "user" field is LOCKED: proposals never change it unless the user
 *   unlocked that field ("Let AI update").
 * - Proposals are applied to form values only; saving is the user's step.
 *
 * Kept free of React and `@/` imports so it can be unit tested with
 * `node --test` (frontend/tests/ai-fill-model.test.ts).
 */
import {
  AI_FLAGS_KEY,
  aiFlagFor,
  readAiFlags,
  withAiFlag,
  withoutAiFlag,
  type AiFlags,
} from "../../components/forms/ai-flags.ts";
import { docToPlain, isRichValue, plainToDoc, richValue } from "../rich-text/rich-model.ts";

export type FieldOrigin = "empty" | "ai" | "user";
export type FillStage = "asking" | "filling" | "ready";
export type FillConfidence = "high" | "medium" | "low";

export interface FillField {
  field_name: string;
  field_type: string;
}

export interface FillProposal {
  field_name: string;
  value: string | null;
  items: string[] | null;
  confidence: FillConfidence;
  source_text?: string | null;
  reason?: string | null;
  over_budget?: boolean;
}

export interface FillQuestion {
  id: string;
  field_names: string[];
}

export interface FormStateItem {
  field_name: string;
  value: string;
  origin: FieldOrigin;
}

export interface FillBudget {
  budget: number;
  unit: "chars" | "items";
  item_budget: number | null;
}

type FormValues = Record<string, unknown>;

/** The assistant never fills these field types. */
export const UNFILLABLE_TYPES = ["signature"];

function cleanItems(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** The plain text of a form value, as the server stores it (lists as a JSON array). */
export function plainFormValue(fieldType: string, value: unknown): string {
  if (fieldType === "list") {
    const items = cleanItems(value);
    return items.length ? JSON.stringify(items) : "";
  }
  if (isRichValue(value)) return docToPlain(value.doc);
  return value === null || value === undefined ? "" : String(value);
}

export function isBlankValue(fieldType: string, value: unknown): boolean {
  return plainFormValue(fieldType, value).trim() === "";
}

/** Who wrote the field's current value. */
export function fieldOrigin(fieldType: string, value: unknown, flags: AiFlags, fieldName: string): FieldOrigin {
  if (isBlankValue(fieldType, value)) return "empty";
  return aiFlagFor(flags, fieldName, value).ai_action === "ai_fill" ? "ai" : "user";
}

/**
 * The form as sent with a chat message: every fillable field with its plain
 * value and origin. An unlocked field is sent as "ai" so the AI may change it.
 */
export function buildFormState(fields: FillField[], values: FormValues, unlocked: ReadonlySet<string>): FormStateItem[] {
  const flags = readAiFlags(values);
  return fields
    .filter((field) => !UNFILLABLE_TYPES.includes(field.field_type))
    .map((field) => {
      const value = values[field.field_name];
      const origin = fieldOrigin(field.field_type, value, flags, field.field_name);
      return {
        field_name: field.field_name,
        value: plainFormValue(field.field_type, value),
        origin: origin === "user" && unlocked.has(field.field_name) ? "ai" : origin,
      };
    });
}

/** A proposal as the form value of its field type (null when it has no usable value). */
export function proposalFormValue(fieldType: string, proposal: FillProposal): unknown {
  if (fieldType === "list") {
    const items = cleanItems(proposal.items ?? (proposal.value ? proposal.value.split("\n") : []));
    return items.length ? items : null;
  }
  const text = proposal.value ?? (proposal.items ? proposal.items.join("\n") : "");
  if (!text.trim()) return null;
  if (fieldType === "textarea") return richValue(plainToDoc(text));
  return fieldType === "date" || fieldType === "number" ? text.trim() : text;
}

export interface ApplyResult {
  /** New form values (including the AI flags entry); the input is not changed. */
  values: FormValues;
  applied: string[];
  /** Proposals left out because the user wrote that field. */
  skippedLocked: string[];
  /** The value each applied field had before (for Undo). */
  previous: Record<string, unknown>;
}

/** Put proposals into the form values. Locked fields are skipped and reported. */
export function applyFillProposals(
  fields: FillField[],
  values: FormValues,
  proposals: FillProposal[],
  unlocked: ReadonlySet<string> = new Set(),
): ApplyResult {
  const types = new Map(fields.map((field) => [field.field_name, field.field_type]));
  const next: FormValues = { ...values };
  let flags = readAiFlags(values);
  const applied: string[] = [];
  const skippedLocked: string[] = [];
  const previous: Record<string, unknown> = {};

  for (const proposal of proposals) {
    const name = proposal.field_name;
    const type = types.get(name);
    if (type === undefined || UNFILLABLE_TYPES.includes(type) || proposal.confidence === "low") continue;
    const value = proposalFormValue(type, proposal);
    if (value === null) continue;
    if (fieldOrigin(type, next[name], flags, name) === "user" && !unlocked.has(name)) {
      skippedLocked.push(name);
      continue;
    }
    previous[name] = values[name];
    next[name] = value;
    flags = withAiFlag(flags, name, "ai_fill", value);
    applied.push(name);
  }
  next[AI_FLAGS_KEY] = flags;
  return { values: next, applied, skippedLocked, previous };
}

/** Undo one applied proposal: the earlier value is back and the field is no longer the AI's. */
export function undoProposal(values: FormValues, fieldName: string, previousValue: unknown): FormValues {
  return {
    ...values,
    [fieldName]: previousValue,
    [AI_FLAGS_KEY]: withoutAiFlag(readAiFlags(values), fieldName),
  };
}

/** The assistant's summary line: fields filled, fields to check, questions. */
export function summarizeTurn(turn: { proposals: FillProposal[]; questions: unknown[] }): {
  filled: number;
  check: number;
  questions: number;
} {
  const kept = turn.proposals.filter((proposal) => proposal.confidence !== "low");
  return {
    filled: kept.length,
    check: kept.filter((proposal) => proposal.confidence === "medium").length,
    questions: turn.questions.length,
  };
}

export function summaryText(summary: { filled: number; check: number; questions: number }): string {
  const parts: string[] = [];
  if (summary.filled) parts.push(`Filled ${summary.filled}`);
  if (summary.check) parts.push(`Check ${summary.check}`);
  if (summary.questions) parts.push(summary.questions === 1 ? "1 question" : `${summary.questions} questions`);
  return parts.join(" · ");
}

export function stageLabel(stage: FillStage | null | undefined): string {
  if (stage === "asking") return "Asking a few questions";
  if (stage === "ready") return "Ready";
  if (stage === "filling") return "Filling the form";
  return "Tell me about your document";
}

export function progressText(filled: number, total: number): string {
  if (total === 0) return "No required fields";
  return `Required: ${filled} of ${total} filled`;
}

/**
 * The body of the next chat message: the text, an answer per open question
 * that was not skipped (the clicked choice, or null when it is answered in
 * the text), the skipped question ids and the form state.
 */
export function nextSendBody(
  message: string,
  openQuestions: FillQuestion[],
  marked: Readonly<Record<string, string>>,
  skipped: ReadonlySet<string>,
  formState: FormStateItem[],
): { message: string; answers: { question_id: string; choice: string | null }[]; skipped: string[]; form_state: FormStateItem[] } {
  const text = message.trim();
  const answers: { question_id: string; choice: string | null }[] = [];
  const skippedIds: string[] = [];
  for (const question of openQuestions) {
    if (skipped.has(question.id)) {
      skippedIds.push(question.id);
      continue;
    }
    const choice = marked[question.id]?.trim() || null;
    if (choice || text) answers.push({ question_id: question.id, choice });
  }
  return { message: text, answers, skipped: skippedIds, form_state: formState };
}

/** Something to send: text, or at least one clicked choice. */
export function canSend(
  message: string,
  openQuestions: FillQuestion[],
  marked: Readonly<Record<string, string>>,
  skipped: ReadonlySet<string>,
): boolean {
  if (message.trim()) return true;
  return openQuestions.some((question) => !skipped.has(question.id) && Boolean(marked[question.id]?.trim()));
}

/** How much of its budget a value uses; null when it fits (or has no budget). */
export function overBudget(
  fieldType: string,
  value: unknown,
  budget: FillBudget | null | undefined,
): { length: number; budget: number; unit: "chars" | "items" } | null {
  if (!budget) return null;
  if (budget.unit === "items") {
    const items = cleanItems(value);
    if (items.length > budget.budget) return { length: items.length, budget: budget.budget, unit: "items" };
    const longest = items.reduce((max, item) => Math.max(max, item.length), 0);
    if (budget.item_budget && longest > budget.item_budget) {
      return { length: longest, budget: budget.item_budget, unit: "chars" };
    }
    return null;
  }
  const length = plainFormValue(fieldType, value).length;
  return length > budget.budget ? { length, budget: budget.budget, unit: "chars" } : null;
}

/** Example first messages for a template, built from its first required field labels. */
export function examplePrompts(fields: { field_label: string | null; field_name: string; is_required: boolean; field_type: string }[]): string[] {
  const labels = fields
    .filter((field) => field.is_required && !UNFILLABLE_TYPES.includes(field.field_type))
    .slice(0, 4)
    .map((field) => (field.field_label?.trim() || field.field_name.replace(/_/g, " ")).toLowerCase());
  const prompts = ["Here is everything I have, in my own words: "];
  if (labels.length >= 2) prompts.push(`My ${labels[0]} is …, ${labels.slice(1).map((label) => `the ${label} is …`).join(", ")}`);
  prompts.push("I'll paste my notes. Ask me about anything that is missing.");
  return prompts;
}

/** Which message, if any, describes a 409 {code: "turn_limit"} error. */
export function turnLimitMessage(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const { status, detail } = error as { status?: number; detail?: unknown };
  if (status !== 409 || !detail || typeof detail !== "object") return null;
  const coded = detail as { code?: unknown; detail?: unknown };
  if (coded.code !== "turn_limit") return null;
  return typeof coded.detail === "string" ? coded.detail : "This chat reached its limit. Clear the chat to start again.";
}
