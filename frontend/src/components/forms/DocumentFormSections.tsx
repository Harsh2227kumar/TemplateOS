import { useMemo } from "react";
import { useFormContext, useWatch, type FieldErrors } from "react-hook-form";
import { CheckCircle2 } from "lucide-react";

import type { DocumentFormValues, TemplateField } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DynamicField, type AiFieldContext } from "./DynamicField";
import { countRequiredFilled, groupFieldsBySection } from "./form-values";

interface DocumentFormSectionsProps {
  fields: TemplateField[];
  aiContext?: AiFieldContext;
  disabled?: boolean;
}

/** Fields grouped into sections, each with a header showing its own progress. */
export function DocumentFormSections({ fields, aiContext, disabled }: DocumentFormSectionsProps) {
  const sections = useMemo(() => groupFieldsBySection(fields), [fields]);
  const showHeaders = sections.length > 1 || sections[0]?.name !== "General";

  if (fields.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        This template has no fields to fill in.
      </p>
    );
  }

  return (
    <div className="space-y-8">
      {sections.map((section) => {
        const headingId = `section-${section.name.replace(/\W+/g, "-").toLowerCase()}`;
        return (
          <section key={section.name} aria-labelledby={showHeaders ? headingId : undefined} className="space-y-4">
            {showHeaders && <SectionHeader id={headingId} name={section.name} fields={section.fields} />}
            <div className="grid gap-x-4 gap-y-5 md:grid-cols-2">
              {section.fields.map((field) => {
                // Long-form inputs always span the full width.
                const wide =
                  section.fields.length === 1 ||
                  ["textarea", "list", "signature"].includes(field.field_type) ||
                  (field.ai_enabled && field.field_type === "text");
                return (
                  <div key={field.field_name} className={cn("min-w-0", wide && "md:col-span-2")}>
                    <DynamicField field={field} aiContext={aiContext} disabled={disabled} />
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function SectionHeader({ id, name, fields }: { id: string; name: string; fields: TemplateField[] }) {
  const { control } = useFormContext<DocumentFormValues>();
  const values = useWatch({ control }) as DocumentFormValues;
  const { filled, total } = countRequiredFilled(fields, values ?? {});
  const complete = total > 0 && filled === total;

  return (
    <div className="flex items-center gap-3 border-b border-slate-200 pb-2">
      <h3 id={id} className="text-sm font-semibold uppercase tracking-wide text-slate-700">
        {name}
      </h3>
      {total > 0 && (
        <span
          className={cn(
            "ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
            complete ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600",
          )}
        >
          {complete && <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
          {filled}/{total} required
        </span>
      )}
    </div>
  );
}

/** "7 of 10 required fields filled" with a progress bar. */
export function FormProgress({ fields }: { fields: TemplateField[] }) {
  const { control } = useFormContext<DocumentFormValues>();
  const values = useWatch({ control }) as DocumentFormValues;
  const { filled, total } = countRequiredFilled(fields, values ?? {});

  if (total === 0) {
    return <p className="text-sm text-slate-500">All fields are optional. Fill in what you need.</p>;
  }

  const percent = Math.round((filled / total) * 100);
  const complete = filled === total;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className={cn("font-medium", complete ? "text-emerald-700" : "text-slate-700")}>
          {complete ? "All required fields filled" : `${filled} of ${total} required fields filled`}
        </span>
        <span className="tabular-nums text-xs text-slate-500">{percent}%</span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label="Required fields filled"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={filled}
        aria-valuetext={`${filled} of ${total} required fields filled`}
      >
        <div
          className={cn("h-full rounded-full transition-all", complete ? "bg-emerald-500" : "bg-blue-600")}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Scrolls to and focuses the first field (in display order) with an error.
 * Returns the field name, or null when no rendered field has an error.
 */
export function focusFirstError(fields: TemplateField[], errors: FieldErrors): string | null {
  const ordered = groupFieldsBySection(fields).flatMap((s) => s.fields);
  const first = ordered.find((f) => errors[f.field_name]);
  if (!first) return null;
  // Wait a frame so error messages have rendered before measuring.
  requestAnimationFrame(() => {
    const container = document.querySelector<HTMLElement>(`[data-field-name="${CSS.escape(first.field_name)}"]`);
    if (!container) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    container.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
    const focusable = container.querySelector<HTMLElement>("input, textarea, select, button:not([aria-disabled])");
    focusable?.focus({ preventScroll: true });
  });
  return first.field_name;
}
