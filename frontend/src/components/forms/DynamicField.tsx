import {
  forwardRef,
  useLayoutEffect,
  useMemo,
  useRef,
  type ComponentProps,
  type ForwardedRef,
  type KeyboardEvent,
} from "react";
import { Controller, useFormContext, type FieldError, type FieldErrors } from "react-hook-form";
import { format, parseISO } from "date-fns";
import { AlertCircle } from "lucide-react";

import { AiActionToolbar } from "@/components/fields/AiActionToolbar";
import { useAiStyleSwitcher } from "@/components/fields/use-ai-style-switcher";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  describeValidationRule,
  isValidIsoDate,
  parseNumber,
  parseValidationRule,
  type ValidationRule,
} from "@/lib/validation";
import { aiFieldKind } from "@/components/fields/ai-style-state";
import { ListField } from "./ListField";

export interface DynamicFieldDefinition {
  field_name: string;
  field_label: string | null;
  field_type: string;
  default_value: string | null;
  is_required: boolean;
  description: string | null;
  example_value: string | null;
  validation_rule: string | null;
  section: string | null;
  ai_enabled?: boolean;
}

export interface AiFieldContext {
  templateId: number;
  /** Saved draft id, or null before the first save. */
  documentId?: number | null;
}

interface DynamicFieldProps {
  field: DynamicFieldDefinition;
  /** Enables the AI style switcher on ai_enabled text/textarea/list fields. */
  aiContext?: AiFieldContext;
  /** Disables input, e.g. while the form is saving. */
  disabled?: boolean;
}

const TEXTAREA_MAX_AUTO_HEIGHT = 480;

/** First error message for a field, whatever shape RHF stored it in. */
export function getFieldErrorMessage(errors: FieldErrors, name: string): string | null {
  const error = errors[name] as (FieldError & { root?: FieldError }) | FieldError[] | undefined;
  if (!error) return null;
  if (Array.isArray(error)) {
    const first = error.find((e) => e?.message);
    return first?.message ? String(first.message) : null;
  }
  if (error.message) return String(error.message);
  if (error.root?.message) return String(error.root.message);
  return null;
}

/**
 * Renders one template field: label with required marker, description,
 * a type-appropriate input, hints (example, rules, character counter), the
 * AI style switcher where enabled, and a single error message.
 */
/**
 * Cleaning may have stored the blank it replaced ("-------", "______") as the
 * example value. Such a hint tells the user nothing, so drop examples that
 * contain no letters or digits.
 */
function usableExample(value: string | null): string | null {
  return value && /[\p{L}\p{N}]/u.test(value) ? value : null;
}

export function DynamicField({ field: rawField, aiContext, disabled }: DynamicFieldProps) {
  const field = useMemo(
    () => ({ ...rawField, example_value: usableExample(rawField.example_value) }),
    [rawField],
  );
  const { formState: { errors } } = useFormContext();
  const name = field.field_name;
  const inputId = `field-${name}`;
  const hintId = `${inputId}-hint`;
  const metaId = `${inputId}-meta`;
  const errorId = `${inputId}-error`;
  const label = field.field_label?.trim() || name;

  const rule = useMemo(() => parseValidationRule(field.validation_rule), [field.validation_rule]);
  const errorMessage = getFieldErrorMessage(errors, name);
  const invalid = errorMessage !== null;
  // Field types the AI text actions apply to (matches the backend).
  const aiKind = aiFieldKind(field.field_type);
  const showAi = !!aiContext && field.ai_enabled === true && aiKind !== null;

  const describedBy = [field.description ? hintId : null, metaId, invalid ? errorId : null]
    .filter(Boolean)
    .join(" ");

  const controlProps: FieldControlProps = {
    field,
    rule,
    inputId,
    metaId,
    describedBy,
    invalid,
    disabled,
    locked: false,
  };

  return (
    <div data-field-name={name} className="min-w-0 space-y-1.5">
      <Label htmlFor={inputId} className="block text-sm font-medium leading-snug text-slate-800">
        {label}
        {field.is_required && (
          <>
            <span className="ml-0.5 text-red-500" aria-hidden="true">*</span>
            <span className="sr-only"> (required)</span>
          </>
        )}
      </Label>
      {field.description && (
        <p id={hintId} className="text-xs leading-snug text-slate-500">
          {field.description}
        </p>
      )}

      {field.field_type === "list" ? (
        <>
          {showAi && aiContext ? (
            <AiListControl
              aiContext={aiContext}
              fieldName={name}
              inputId={inputId}
              label={label}
              placeholder={field.example_value}
              maxItems={rule.max}
              invalid={invalid}
              describedBy={describedBy}
              disabled={disabled}
            />
          ) : (
            <ListField
              fieldName={name}
              inputId={inputId}
              label={label}
              placeholder={field.example_value}
              maxItems={rule.max}
              invalid={invalid}
              describedBy={describedBy}
              disabled={disabled}
            />
          )}
          <span id={metaId} className="sr-only">
            {describeValidationRule(field) ?? ""}
          </span>
        </>
      ) : showAi && aiContext ? (
        <AiFieldControl {...controlProps} aiContext={aiContext} label={label} />
      ) : (
        <FieldControl {...controlProps} />
      )}

      {errorMessage && (
        <p id={errorId} className="flex items-start gap-1 text-sm text-red-600" role="alert">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      )}
    </div>
  );
}

interface FieldControlProps {
  field: DynamicFieldDefinition;
  rule: ValidationRule;
  inputId: string;
  metaId: string;
  describedBy: string;
  invalid: boolean;
  disabled?: boolean;
  /** Read-only while an AI request runs, so typing cannot be overwritten. */
  locked: boolean;
}

function AiFieldControl({
  aiContext,
  label,
  ...props
}: FieldControlProps & { aiContext: AiFieldContext; label: string }) {
  const kind = props.field.field_type === "textarea" ? "multiline" : "text";
  const switcher = useAiStyleSwitcher({
    fieldName: props.field.field_name,
    fieldLabel: label,
    kind,
    templateId: aiContext.templateId,
    documentId: aiContext.documentId,
  });
  return (
    <>
      <FieldControl {...props} locked={switcher.isPending} />
      <AiActionToolbar switcher={switcher} controlsId={props.inputId} disabled={props.disabled} kind={kind} />
    </>
  );
}

/** A list field with the AI style switcher; every item is rewritten on its own. */
function AiListControl({
  aiContext,
  ...props
}: ComponentProps<typeof ListField> & { aiContext: AiFieldContext }) {
  const switcher = useAiStyleSwitcher({
    fieldName: props.fieldName,
    fieldLabel: props.label,
    kind: "list",
    templateId: aiContext.templateId,
    documentId: aiContext.documentId,
  });
  return (
    <>
      <ListField {...props} disabled={props.disabled || switcher.isPending} />
      <AiActionToolbar switcher={switcher} controlsId={props.inputId} disabled={props.disabled} kind="list" />
    </>
  );
}

function FieldControl({ field, rule, inputId, metaId, describedBy, invalid, disabled, locked }: FieldControlProps) {
  const { control } = useFormContext();
  const type = field.field_type;

  return (
    <Controller
      name={field.field_name}
      control={control}
      render={({ field: controller }) => {
        const text = typeof controller.value === "string" ? controller.value : controller.value == null ? "" : String(controller.value);
        const common = {
          id: inputId,
          name: controller.name,
          onBlur: controller.onBlur,
          disabled,
          readOnly: locked,
          "aria-busy": locked || undefined,
          "aria-invalid": invalid || undefined,
          "aria-describedby": describedBy || undefined,
          "aria-required": field.is_required || undefined,
        };
        const stateClass = cn(
          invalid && "border-red-500 focus-visible:ring-red-500",
          locked && "cursor-progress bg-violet-50/50 text-slate-500",
        );
        const placeholder = field.example_value || undefined;

        let input: JSX.Element;
        switch (type) {
          case "textarea":
            input = (
              <AutoGrowTextarea
                {...common}
                ref={controller.ref}
                value={text}
                onChange={(e) => controller.onChange(e.target.value)}
                placeholder={placeholder}
                className={stateClass}
              />
            );
            break;

          case "number":
            input = (
              <NumberInput
                {...common}
                ref={controller.ref}
                value={text}
                rule={rule}
                onValueChange={controller.onChange}
                placeholder={placeholder}
                className={cn("tabular-nums", stateClass)}
              />
            );
            break;

          case "date": {
            const isoValue = isValidIsoDate(text) ? text : "";
            input = (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    {...common}
                    ref={controller.ref}
                    type="date"
                    value={isoValue}
                    onChange={(e) => controller.onChange(e.target.value)}
                    className={cn("w-full sm:w-52", stateClass)}
                  />
                  {!disabled && (
                    <button
                      type="button"
                      className="rounded px-1.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      onClick={() => controller.onChange(format(new Date(), "yyyy-MM-dd"))}
                    >
                      Today
                    </button>
                  )}
                </div>
                {isoValue ? (
                  <p className="text-xs text-slate-500">{format(parseISO(isoValue), "EEEE, d MMMM yyyy")}</p>
                ) : text.trim() ? (
                  <p className="text-xs text-amber-700">
                    The saved value “{text}” isn't a calendar date. Pick a date to replace it.
                  </p>
                ) : null}
              </div>
            );
            break;
          }

          case "email":
            input = (
              <Input
                {...common}
                ref={controller.ref}
                type="email"
                inputMode="email"
                autoComplete="email"
                value={text}
                onChange={(e) => controller.onChange(e.target.value)}
                placeholder={placeholder ?? "name@example.com"}
                className={stateClass}
              />
            );
            break;

          case "signature":
            input = (
              <div className="rounded-md border border-dashed border-slate-300 bg-slate-50/60 p-3">
                <Input
                  {...common}
                  ref={controller.ref}
                  type="text"
                  autoComplete="name"
                  value={text}
                  onChange={(e) => controller.onChange(e.target.value)}
                  placeholder={placeholder ?? "Type your full name"}
                  className={cn("h-12 bg-white font-serif text-xl italic", stateClass)}
                />
                <p className="mt-1.5 text-xs text-slate-500">
                  Typed signature. A drawing pad is planned for a later version.
                </p>
              </div>
            );
            break;

          default:
            input = (
              <Input
                {...common}
                ref={controller.ref}
                type="text"
                value={text}
                onChange={(e) => controller.onChange(e.target.value)}
                placeholder={placeholder}
                className={stateClass}
              />
            );
        }

        return (
          <>
            {input}
            <FieldMeta field={field} rule={rule} text={text} metaId={metaId} />
          </>
        );
      }}
    />
  );
}

/** Example value, rule hint and (for length-limited text) a character counter. */
function FieldMeta({
  field,
  rule,
  text,
  metaId,
}: {
  field: DynamicFieldDefinition;
  rule: ValidationRule;
  text: string;
  metaId: string;
}) {
  const ruleHint = describeValidationRule(field);
  const showExample =
    !!field.example_value &&
    field.field_type !== "date" &&
    field.field_type !== "signature" &&
    field.example_value !== field.description;
  const hasCounter =
    rule.max !== undefined && ["text", "textarea", "signature"].includes(field.field_type);
  const length = text.length;

  if (!showExample && !ruleHint && !hasCounter) {
    return <span id={metaId} className="sr-only" />;
  }

  return (
    <div id={metaId} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-0.5 text-xs text-slate-500">
      <span className="min-w-0 break-words">
        {showExample && (
          <>
            <span className="font-medium text-slate-600">e.g.</span> {field.example_value}
          </>
        )}
        {showExample && ruleHint && !hasCounter && " · "}
        {ruleHint && !hasCounter && ruleHint}
      </span>
      {hasCounter && (
        <span
          className={cn(
            "ml-auto shrink-0 tabular-nums",
            length > rule.max! ? "font-medium text-red-600" : length > rule.max! * 0.9 ? "text-amber-700" : "",
          )}
        >
          <span className="sr-only">Characters used: </span>
          {length.toLocaleString()} / {rule.max!.toLocaleString()}
          {rule.min !== undefined && length < rule.min && length > 0 && ` (min ${rule.min})`}
        </span>
      )}
    </div>
  );
}

function assignRef<T>(ref: ForwardedRef<T>, el: T | null) {
  if (typeof ref === "function") ref(el);
  else if (ref) ref.current = el;
}

/** Textarea that grows with its content up to a max height, then scrolls. */
const AutoGrowTextarea = forwardRef<HTMLTextAreaElement, ComponentProps<typeof Textarea>>(
  ({ className, value, ...props }, ref) => {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);

    useLayoutEffect(() => {
      const el = innerRef.current;
      if (!el) return;
      el.style.height = "auto";
      // +2 for the 1px top/bottom border (border-box sizing).
      const target = el.scrollHeight + 2;
      el.style.height = `${Math.min(target, TEXTAREA_MAX_AUTO_HEIGHT)}px`;
      el.style.overflowY = target > TEXTAREA_MAX_AUTO_HEIGHT ? "auto" : "hidden";
    }, [value]);

    return (
      <Textarea
        {...props}
        ref={(el) => {
          innerRef.current = el;
          assignRef(ref, el);
        }}
        value={value}
        rows={3}
        className={cn("min-h-[88px] resize-y leading-relaxed", className)}
      />
    );
  },
);
AutoGrowTextarea.displayName = "AutoGrowTextarea";

type NumberInputProps = Omit<ComponentProps<typeof Input>, "onChange" | "value" | "type"> & {
  value: string;
  rule: ValidationRule;
  onValueChange: (value: string) => void;
};

/**
 * Numeric input kept as the exact text the user typed (no type="number":
 * browsers report partial input like "1e" as "" there, silently losing it).
 * ArrowUp/ArrowDown step by 1 within the min/max rule.
 */
const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  ({ value, rule, onValueChange, onKeyDown, ...props }, ref) => {
    const step = (event: KeyboardEvent<HTMLInputElement>) => {
      if (props.readOnly || props.disabled) return;
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      const current = parseNumber(value);
      let next = current === null ? (rule.min ?? 0) : current + (event.key === "ArrowUp" ? 1 : -1);
      if (rule.min !== undefined) next = Math.max(rule.min, next);
      if (rule.max !== undefined) next = Math.min(rule.max, next);
      // Avoid float noise like 0.30000000000000004.
      onValueChange(String(Math.round(next * 1e9) / 1e9));
    };

    return (
      <Input
        {...props}
        ref={ref}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        onKeyDown={(e) => {
          step(e);
          onKeyDown?.(e);
        }}
        role="spinbutton"
        aria-valuemin={rule.min}
        aria-valuemax={rule.max}
        aria-valuenow={parseNumber(value) ?? undefined}
      />
    );
  },
);
NumberInput.displayName = "NumberInput";
