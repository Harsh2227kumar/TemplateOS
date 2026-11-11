import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, FilePenLine, X } from "lucide-react";

import type { FitReport } from "@/lib/api";

function dismissKey(documentId: number, version: number | null): string {
  return `templateos.fit.dismissed.${documentId}.${version ?? "latest"}`;
}

function wasDismissed(key: string): boolean {
  try {
    return window.sessionStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

interface FitCheckNoticeProps {
  documentId: number;
  fit: FitReport | null | undefined;
  /** Jump to a field of the form. */
  onShowField: (fieldName: string) => void;
  /** The Word editor page for the latest version (null: editor off). */
  editFileHref?: string | null;
}

/**
 * V1.7 P2.2: after generating, says when the content does not fit the
 * template (more pages than the template's baseline, or fields longer than
 * their place in the document). Advisory: the user can shorten the fields,
 * fix the layout in Word, or keep the document as it is.
 */
export function FitCheckNotice({ documentId, fit, onShowField, editFileHref = null }: FitCheckNoticeProps) {
  const key = dismissKey(documentId, fit?.version ?? null);
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);
  if (!fit || (!fit.overflow && fit.long_fields.length === 0)) return null;
  if (dismissedKey === key || wasDismissed(key)) return null;

  const extraPages = fit.overflow && fit.pages !== null && fit.baseline_pages !== null ? fit.pages - fit.baseline_pages : 0;
  const dismiss = () => {
    try {
      window.sessionStorage.setItem(key, "1");
    } catch {
      // Not stored: the notice is hidden until the page reloads.
    }
    setDismissedKey(key);
  };

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="font-medium">
            {extraPages > 0
              ? `Version ${fit.version} is ${extraPages} page${extraPages === 1 ? "" : "s"} longer than the template (${fit.pages} instead of ${fit.baseline_pages}).`
              : `Some fields of version ${fit.version} are longer than their space in the document.`}
          </p>
          {fit.long_fields.length > 0 && (
            <ul className="space-y-1">
              {fit.long_fields.map((field) => (
                <li key={field.field_name} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="break-words">
                    {field.label}: {field.length.toLocaleString()} / {field.budget.toLocaleString()}{" "}
                    {field.unit === "items" ? "items" : "characters"}
                  </span>
                  <button
                    type="button"
                    onClick={() => onShowField(field.field_name)}
                    className="rounded text-xs font-medium underline underline-offset-2 hover:text-amber-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    Shorten it
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-amber-800">
            Shorten the fields (the Concise style can help), save and generate again
            {editFileHref ? ", or fix the layout in Word." : "."}
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {editFileHref && (
              <Link
                to={editFileHref}
                className="inline-flex items-center gap-1 text-xs font-medium underline underline-offset-2 hover:text-amber-950"
              >
                <FilePenLine className="h-3.5 w-3.5" aria-hidden="true" />
                Fix it in Word
              </Link>
            )}
            <button
              type="button"
              onClick={dismiss}
              className="rounded text-xs font-medium underline underline-offset-2 hover:text-amber-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              Keep as it is
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="rounded p-0.5 text-amber-700 hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
