import { useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import { Controller, useFormContext } from "react-hook-form";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listExampleItems } from "@/lib/list-example";
import { cleanListItems } from "@/lib/validation";
import { cn } from "@/lib/utils";

interface ListFieldProps {
  fieldName: string;
  /** Used for the first input's id so the field label focuses it. */
  inputId: string;
  label: string;
  /** The field's example value; a JSON array gives one placeholder per item. */
  placeholder?: string | null;
  maxItems?: number;
  invalid?: boolean;
  describedBy?: string;
  disabled?: boolean;
}

let nextKey = 1;
const newKey = () => `item-${nextKey++}`;

/**
 * Editable list of short text items, stored in the form as string[].
 *
 * The form value is the single source of truth (no mirrored local state, so
 * form.reset() and Reset Form just work). An empty list still shows one
 * input to type into; blank items are allowed while editing and dropped on
 * save. Keyboard: Enter adds an item below, Backspace in an empty item
 * removes it, Alt+ArrowUp/ArrowDown reorders.
 */
export function ListField(props: ListFieldProps) {
  const { control } = useFormContext();
  return (
    <Controller
      name={props.fieldName}
      control={control}
      render={({ field }) => (
        <ListEditor
          {...props}
          value={Array.isArray(field.value) ? (field.value as unknown[]).map((v) => (typeof v === "string" ? v : String(v ?? ""))) : []}
          onChange={field.onChange}
          onBlur={field.onBlur}
        />
      )}
    />
  );
}

interface ListEditorProps extends ListFieldProps {
  value: string[];
  onChange: (value: string[]) => void;
  onBlur: () => void;
}

function ListEditor({
  value,
  onChange,
  onBlur,
  inputId,
  label,
  placeholder,
  maxItems,
  invalid,
  describedBy,
  disabled,
}: ListEditorProps) {
  // Always show at least one row to type into.
  const rows = value.length > 0 ? value : [""];
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);
  const focusIndexRef = useRef<number | null>(null);

  // Stable React keys per row, so focus and text don't jump on insert/remove.
  // Rebuilt when the list changes length from outside (form reset).
  const keysRef = useRef<string[]>([]);
  if (keysRef.current.length !== rows.length) {
    keysRef.current = rows.map((_, i) => keysRef.current[i] ?? newKey());
  }

  useEffect(() => {
    const index = focusIndexRef.current;
    if (index === null) return;
    focusIndexRef.current = null;
    const el = inputRefs.current[Math.min(index, rows.length - 1)];
    el?.focus();
  });

  const examples = useMemo(() => listExampleItems(placeholder), [placeholder]);
  const filledCount = cleanListItems(value).length;
  const atMax = maxItems !== undefined && rows.length >= maxItems;

  const commit = (nextRows: string[], nextKeys: string[], focusIndex?: number) => {
    keysRef.current = nextKeys.length > 0 ? nextKeys : [newKey()];
    if (focusIndex !== undefined) focusIndexRef.current = focusIndex;
    onChange(nextRows);
  };

  const update = (index: number, text: string) => {
    const next = [...rows];
    next[index] = text;
    commit(next, [...keysRef.current]);
  };

  const insertAfter = (index: number) => {
    if (atMax) return;
    const next = [...rows];
    next.splice(index + 1, 0, "");
    const keys = [...keysRef.current];
    keys.splice(index + 1, 0, newKey());
    commit(next, keys, index + 1);
  };

  const remove = (index: number) => {
    const next = rows.filter((_, i) => i !== index);
    const keys = keysRef.current.filter((_, i) => i !== index);
    commit(next, keys, Math.max(0, index - 1));
  };

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const next = [...rows];
    const keys = [...keysRef.current];
    [next[index], next[target]] = [next[target], next[index]];
    [keys[index], keys[target]] = [keys[target], keys[index]];
    commit(next, keys, target);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key === "Enter") {
      // Never submit the whole form from a list item.
      event.preventDefault();
      if (event.nativeEvent.isComposing) return;
      if (rows[index].trim() === "" && index === rows.length - 1) return; // no stacking blanks
      insertAfter(index);
    } else if (event.key === "Backspace" && rows[index] === "" && rows.length > 1) {
      event.preventDefault();
      remove(index);
    } else if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault();
      move(index, event.key === "ArrowUp" ? -1 : 1);
    }
  };

  return (
    <div className="space-y-2">
      <ol className="space-y-2" aria-label={`${label} items`}>
        {rows.map((item, index) => {
          const onlyEmptyRow = rows.length === 1 && item === "";
          return (
            <li key={keysRef.current[index]} className="flex items-center gap-1.5">
              <span className="w-5 shrink-0 text-right text-xs tabular-nums text-slate-400" aria-hidden="true">
                {index + 1}.
              </span>
              <Input
                ref={(el) => {
                  inputRefs.current[index] = el;
                }}
                id={index === 0 ? inputId : undefined}
                value={item}
                disabled={disabled}
                onChange={(e) => update(index, e.target.value)}
                onBlur={onBlur}
                onKeyDown={(e) => handleKeyDown(e, index)}
                placeholder={examples[index] ?? `Item ${index + 1}`}
                aria-label={`${label}, item ${index + 1} of ${rows.length}`}
                aria-invalid={invalid || undefined}
                aria-describedby={describedBy}
                className={cn("min-w-0 flex-1", invalid && "border-red-500 focus-visible:ring-red-500")}
              />
              <div className="flex shrink-0 items-center">
                {rows.length > 1 && (
                  <>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="hidden h-8 w-8 text-slate-500 sm:inline-flex"
                      onClick={() => move(index, -1)}
                      disabled={disabled || index === 0}
                      aria-label={`Move item ${index + 1} up`}
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="hidden h-8 w-8 text-slate-500 sm:inline-flex"
                      onClick={() => move(index, 1)}
                      disabled={disabled || index === rows.length - 1}
                      aria-label={`Move item ${index + 1} down`}
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className={cn("h-8 w-8 text-red-500 hover:text-red-700", onlyEmptyRow && "invisible")}
                  onClick={() => remove(index)}
                  disabled={disabled || onlyEmptyRow}
                  aria-label={`Remove item ${index + 1}`}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const last = rows.length - 1;
            // Reuse a trailing blank item instead of stacking another one.
            if (rows[last].trim() === "") inputRefs.current[last]?.focus();
            else insertAfter(last);
          }}
          disabled={disabled || (atMax && rows[rows.length - 1].trim() !== "")}
          className="h-8"
        >
          <Plus className="mr-1 h-4 w-4" />
          Add item
        </Button>
        <span className="text-xs text-slate-500">
          {filledCount} {filledCount === 1 ? "item" : "items"}
          {maxItems !== undefined && ` of ${maxItems} max`}
          <span className="hidden sm:inline"> · Enter adds the next item</span>
        </span>
      </div>
    </div>
  );
}
