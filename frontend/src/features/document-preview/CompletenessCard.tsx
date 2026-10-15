import { CheckCircle2, CircleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import type { DocumentPreview } from "@/lib/api";
import { cn } from "@/lib/utils";

import { completenessLabel, completenessPercent, isComplete, missingFieldLinks } from "./preview-model";

interface CompletenessCardProps {
  preview: DocumentPreview;
}

/** Required-field meter with links that jump to each missing field on the edit page. */
export function CompletenessCard({ preview }: CompletenessCardProps) {
  const { completeness, permissions } = preview;
  const percent = completenessPercent(completeness);
  const complete = isComplete(completeness);
  const label = completenessLabel(completeness);
  const missing = missingFieldLinks(preview);

  return (
    <Card>
      <CardContent className="space-y-3 p-4 sm:p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          {complete ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          ) : (
            <CircleAlert className="h-4 w-4 text-amber-600" aria-hidden="true" />
          )}
          Completeness
        </h2>
        <div
          role="progressbar"
          aria-label="Required fields filled"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-valuetext={label}
          className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
        >
          <div
            className={cn("h-full rounded-full transition-all", complete ? "bg-emerald-500" : "bg-blue-600")}
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className={cn("text-sm", complete ? "text-emerald-700" : "text-slate-700")}>{label}</p>
        {missing.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Missing</p>
            <ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
              {missing.map((m) => (
                <li key={m.fieldName} className="min-w-0 break-words">
                  {permissions.can_edit ? (
                    <Link
                      to={m.href}
                      className="font-medium text-blue-700 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                    >
                      {m.label}
                    </Link>
                  ) : (
                    <span className="text-slate-700">{m.label}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
