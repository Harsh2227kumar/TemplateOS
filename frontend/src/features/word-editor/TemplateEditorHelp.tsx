import { useState } from "react";
import { Check, Copy, Info } from "lucide-react";

import type { TemplateField } from "@/lib/api";

import { placeholderText } from "./editor-review-model";

/** Side panel of the template file editor: how to add a field, and the existing ones. */
export function TemplateEditorHelp({ fields }: { fields: TemplateField[] }) {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (name: string) => {
    try {
      await navigator.clipboard.writeText(placeholderText(name));
      setCopied(name);
      window.setTimeout(() => setCopied((current) => (current === name ? null : current)), 1500);
    } catch {
      setCopied(null);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <div className="space-y-2">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900">
          <Info className="h-4 w-4 text-slate-500" aria-hidden="true" />
          Add a field
        </h2>
        <p className="text-slate-600">
          Type a blank after its label, e.g. <span className="font-mono text-slate-900">Date of meeting: ________</span>,
          or type <span className="font-mono text-slate-900">{"{{ field_name }}"}</span>.
        </p>
        <p className="text-amber-800">
          Do not change text inside <span className="font-mono">{"{{ }}"}</span> or{" "}
          <span className="font-mono">{"{% %}"}</span>.
        </p>
      </div>
      {fields.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Existing fields</h3>
          <p className="text-xs text-slate-500">Click to copy the placeholder.</p>
          <ul className="flex flex-wrap gap-1.5">
            {fields.map((field) => (
              <li key={field.field_name}>
                <button
                  type="button"
                  onClick={() => void copy(field.field_name)}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  title={placeholderText(field.field_name)}
                  aria-label={`Copy ${placeholderText(field.field_name)}`}
                >
                  {copied === field.field_name ? (
                    <Check className="h-3 w-3 shrink-0 text-emerald-600" aria-hidden="true" />
                  ) : (
                    <Copy className="h-3 w-3 shrink-0" aria-hidden="true" />
                  )}
                  <span className="truncate">{field.field_label?.trim() || field.field_name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
