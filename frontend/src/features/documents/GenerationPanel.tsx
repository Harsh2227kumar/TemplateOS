import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, CheckCircle2, Download, FileOutput, Info, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { GeneratedInfo } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

import { generateActionLabel, pdfStatusLabel, type DownloadFormat } from "./generation";

interface GenerationPanelProps {
  generated: GeneratedInfo | null;
  /** The form has unsaved changes (they are saved before generating). */
  isDirty: boolean;
  generating: boolean;
  retryingPdf: boolean;
  /** Format currently downloading, if any. */
  downloading: DownloadFormat | null;
  /** Saving or another action that should block generation. */
  disabled: boolean;
  error: string | null;
  onGenerate: () => void;
  onRetryPdf: () => void;
  onDownload: (format: DownloadFormat) => void;
}

/**
 * Edit-draft panel for V1.6 generation: the Generate / Regenerate action,
 * progress, and the result (DOCX download, PDF download / retry / notice).
 */
export function GenerationPanel({
  generated,
  isDirty,
  generating,
  retryingPdf,
  downloading,
  disabled,
  error,
  onGenerate,
  onRetryPdf,
  onDownload,
}: GenerationPanelProps) {
  const generatedDate = parseServerDate(generated?.generated_at);
  const stale = Boolean(generated && (generated.is_stale || isDirty));
  const label = generateActionLabel(Boolean(generated), stale);
  const busy = generating || retryingPdf;

  return (
    <Card aria-live="polite">
      <CardContent className="space-y-4 p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <FileOutput className="h-4 w-4 text-slate-500" aria-hidden="true" />
              Final document
            </h2>
            {generated ? (
              <p className="text-sm text-slate-600">
                Generated{" "}
                <span title={generatedDate ? generatedDate.toLocaleString() : undefined}>
                  {generatedDate ? formatDistanceToNow(generatedDate, { addSuffix: true }) : "earlier"}
                </span>
                {generated.template_version ? ` · template v${generated.template_version}` : null}
              </p>
            ) : (
              <p className="text-sm text-slate-600">
                Create the final Word document (and a PDF when available) from your saved values.
              </p>
            )}
          </div>
          <Button
            type="button"
            onClick={onGenerate}
            disabled={disabled || busy}
            variant={generated && !stale ? "outline" : "default"}
            className="w-full shrink-0 sm:w-auto"
          >
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                {generated && <RefreshCw className="h-4 w-4" aria-hidden="true" />}
                {isDirty ? `Save & ${label.charAt(0).toLowerCase()}${label.slice(1)}` : label}
              </>
            )}
          </Button>
        </div>

        {generating && (
          <div className="space-y-2" role="status">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-slate-400" />
            </div>
            <p className="text-xs text-slate-500">
              Filling the template with your values. PDF conversion can take a few more seconds.
            </p>
          </div>
        )}

        {error && !generating && (
          <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3" role="alert">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
            <p className="break-words text-sm text-red-800">{error}</p>
          </div>
        )}

        {generated && !generating && (
          <div className="space-y-3">
            {stale && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
                <p className="text-sm text-amber-800">
                  {isDirty
                    ? "You have unsaved changes. The generated file does not include them yet."
                    : "Values changed after the last generation. Regenerate to include them."}
                </p>
              </div>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              <Button
                type="button"
                variant="secondary"
                onClick={() => onDownload("docx")}
                disabled={downloading !== null}
                className="w-full sm:w-auto"
              >
                {downloading === "docx" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Download DOCX
              </Button>
              {generated.pdf_status === "ok" && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => onDownload("pdf")}
                  disabled={downloading !== null}
                  className="w-full sm:w-auto"
                >
                  {downloading === "pdf" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  Download PDF
                </Button>
              )}
              {generated.pdf_status === "ok" && (
                <span className="flex items-center gap-1 text-xs text-green-700">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {pdfStatusLabel("ok")}
                </span>
              )}
            </div>
            {generated.pdf_status === "failed" && (
              <div className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
                  <p className="text-sm text-amber-800">
                    {pdfStatusLabel("failed")}
                    {generated.pdf_error ? `: ${generated.pdf_error}` : ""}. The DOCX is ready.
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onRetryPdf}
                  disabled={busy || disabled}
                  className="w-full shrink-0 sm:w-auto"
                >
                  {retryingPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Retry PDF
                </Button>
              </div>
            )}
            {generated.pdf_status === "not_configured" && (
              <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="flex items-start gap-1.5 text-xs text-slate-600">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    PDF conversion was not set up when this was generated; the DOCX is ready. If the server now has a
                    PDF converter, create the PDF without regenerating.
                  </span>
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onRetryPdf}
                  disabled={busy || disabled}
                  className="w-full shrink-0 sm:w-auto"
                >
                  {retryingPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Create PDF
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
