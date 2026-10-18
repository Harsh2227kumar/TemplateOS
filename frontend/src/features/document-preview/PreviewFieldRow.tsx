import { AiBadge } from "@/components/fields/AiBadge";
import { RichTextViewer } from "@/features/rich-text/RichTextViewer";
import type { RichDoc } from "@/features/rich-text/rich-model";
import type { PreviewField } from "@/lib/api";

import { fieldDisplay } from "./preview-model";

interface PreviewFieldRowProps {
  field: PreviewField;
}

/**
 * One read-only label / value pair (render inside a <dl>). The value is the
 * backend's display_value / items as-is; rich text renders read-only with
 * its formatting (lazy viewer, plain text until it loads). An "AI" badge
 * marks values written with AI.
 */
export function PreviewFieldRow({ field }: PreviewFieldRowProps) {
  const display = fieldDisplay(field);
  const label = field.label?.trim() || field.field_name;

  return (
    <div className="min-w-0 py-3 sm:grid sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)] sm:gap-4">
      <dt className="break-words text-sm font-medium text-slate-500">
        {label}
        {field.is_required && (
          <>
            <span className="ml-0.5 text-red-500" aria-hidden="true">*</span>
            <span className="sr-only"> (required)</span>
          </>
        )}
        {field.ai_modified && !field.is_empty && <AiBadge action={field.ai_action} />}
      </dt>
      <dd className="mt-1 min-w-0 break-words text-sm text-slate-900 sm:mt-0">
        {(() => {
          switch (display.kind) {
            case "list":
              return (
                <ol className="list-decimal space-y-1 pl-5">
                  {(display.items ?? []).map((item, index) => (
                    <li key={index} className="whitespace-pre-wrap break-words">
                      {item}
                    </li>
                  ))}
                </ol>
              );
            case "rich":
              return <RichTextViewer doc={display.doc as RichDoc} fallbackText={display.text ?? ""} label={label} />;
            case "multiline":
              return <p className="whitespace-pre-wrap break-words">{display.text}</p>;
            case "text":
              return <p className="break-words">{display.text}</p>;
            case "empty":
            default:
              return (
                <span className="flex flex-wrap items-center gap-2">
                  <span className="italic text-slate-400">Not filled</span>
                  {field.missing_required && (
                    <span className="rounded bg-red-50 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-red-700">
                      Required
                    </span>
                  )}
                </span>
              );
          }
        })()}
      </dd>
    </div>
  );
}
