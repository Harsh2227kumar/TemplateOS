import { formatDistanceToNow } from "date-fns";
import { ChevronLeft, Loader2, Pencil, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { latestTimestamp } from "@/features/documents/draft-timestamps";
import { generateActionLabel } from "@/features/documents/generation";
import type { DocumentPreview } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

import { previewTitle } from "./preview-model";

interface PreviewHeaderProps {
  preview: DocumentPreview;
  generating: boolean;
  /** Another action (retry PDF) blocks generation. */
  busy: boolean;
  onGenerate: () => void;
}

function statusClass(status: string): string {
  switch (status) {
    case "draft":
      return "bg-yellow-100 text-yellow-700";
    case "active":
      return "bg-green-100 text-green-700";
    default:
      return "bg-blue-100 text-blue-700";
  }
}

/** Name, status, template, "Last saved", and the Edit / Generate actions. */
export function PreviewHeader({ preview, generating, busy, onGenerate }: PreviewHeaderProps) {
  const { document, template, generation, permissions } = preview;
  const savedAt = latestTimestamp([document.updated_at]);
  const savedDate = parseServerDate(savedAt);
  const savedLabel = savedDate ? formatDistanceToNow(savedDate, { addSuffix: true }) : "unknown";
  const generateLabel = generateActionLabel(Boolean(generation), Boolean(generation?.is_stale));
  const needsGenerate = !generation || generation.is_stale || !generation.docx_available;

  return (
    <div className="space-y-2">
      <Button asChild variant="ghost" size="sm" className="-ml-2 h-8 px-2 text-slate-600">
        <Link to="/">
          <ChevronLeft className="mr-1 h-4 w-4" />
          Dashboard
        </Link>
      </Button>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="break-words text-2xl font-bold text-slate-900">{previewTitle(document.name)}</h1>
            <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusClass(document.status)}`}>
              {document.status.replace("_", " ")}
            </span>
          </div>
          <p className="break-words text-sm text-slate-500">
            Template: {template.name} ·{" "}
            <span title={savedDate ? savedDate.toLocaleString() : undefined}>Last saved {savedLabel}</span>
          </p>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:flex-row">
          {permissions.can_edit && (
            <Button asChild variant="outline" className="w-full sm:w-auto">
              <Link to={`/documents/${document.id}/edit`}>
                <Pencil className="h-4 w-4" aria-hidden="true" />
                Edit
              </Link>
            </Button>
          )}
          {permissions.can_generate && (
            <Button
              type="button"
              onClick={onGenerate}
              disabled={generating || busy}
              variant={needsGenerate ? "default" : "outline"}
              className="w-full sm:w-auto"
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  {generation && <RefreshCw className="h-4 w-4" aria-hidden="true" />}
                  {generateLabel}
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
