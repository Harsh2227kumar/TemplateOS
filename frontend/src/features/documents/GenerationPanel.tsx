import { formatDistanceToNow } from "date-fns";
import { Link } from "react-router-dom";
import { AlertTriangle, Download, FileOutput, FilePenLine, FileText, Info, Loader2, RefreshCw, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { GeneratedInfo } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

import {
  EARLIER_PDF_NOTE,
  generateActionLabel,
  pdfRowView,
  SLOW_PDF_HINT,
  type DownloadFormat,
  type PdfState,
} from "./generation";
import { useSlowHint } from "./use-slow-hint";

interface GenerationPanelProps {
  generated: GeneratedInfo | null;
  /** The form has unsaved changes (they are saved before generating). */
  isDirty: boolean;
  generating: boolean;
  retryingPdf: boolean;
  /** Format currently downloading, if any. */
  downloading: DownloadFormat | null;
  /** Saving or another action that should block generation and Retry PDF. */
  disabled: boolean;
  error: string | null;
  onGenerate: () => void;
  onRetryPdf: () => void;
  onDownload: (format: DownloadFormat) => void;
  /** V1.7 P2.1: the Word editor page for the latest version (hidden when null). */
  editFileHref?: string | null;
}

/**
 * Edit-draft panel for V1.6 generation: the Generate / Regenerate action,
 * progress, and the result as two file rows: the DOCX (download) and the
 * PDF with its own status (ready / not available + reason / retry).
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
  editFileHref = null,
}: GenerationPanelProps) {
  const generatedDate = parseServerDate(generated?.generated_at);
  const stale = Boolean(generated && (generated.is_stale || isDirty));
  const label = generateActionLabel(Boolean(generated), stale);
  const slowHint = useSlowHint(generating);

  return (
    <Card>
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
                Create the final Word document and its PDF from your saved values.
              </p>
            )}
          </div>
          <Button
            type="button"
            onClick={onGenerate}
            disabled={disabled || generating || retryingPdf}
            variant={generated && !stale ? "outline" : "default"}
            className="w-full shrink-0 sm:w-auto"
          >
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating DOCX and PDF…
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
            <p className="text-xs text-slate-500">Filling the template with your values, then converting it to PDF.</p>
            {slowHint && <p className="text-xs text-slate-500">{SLOW_PDF_HINT}</p>}
          </div>
        )}

        {error && !generating && (
          <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3" role="alert">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
            <p className="break-words text-sm text-red-800">{error}</p>
          </div>
        )}

        {generated && !generating && stale && (
          <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
            <p className="text-sm text-amber-800">
              {isDirty
                ? "You have unsaved changes. The generated file does not include them yet."
                : "Values changed after the last generation. Regenerate to include them."}
            </p>
          </div>
        )}

        {(generated || generating) && (
          <ul className="space-y-2" aria-label="Generated files">
            {generated && !generating && (
              <DocxRow
                downloading={downloading === "docx"}
                downloadDisabled={downloading !== null}
                onDownload={() => onDownload("docx")}
                editHref={editFileHref}
              />
            )}
            <PdfRow
              generated={generated}
              generating={generating}
              retrying={retryingPdf}
              downloading={downloading === "pdf"}
              downloadDisabled={downloading !== null}
              retryDisabled={disabled || generating || retryingPdf}
              onDownload={() => onDownload("pdf")}
              onRetry={onRetryPdf}
            />
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export interface DocxRowProps {
  downloading: boolean;
  downloadDisabled: boolean;
  onDownload: () => void;
  /** V1.7 P2.1: "Edit Word file" link (the latest version). */
  editHref?: string | null;
}

/** The generated Word file row (shared with the V1.7 preview page). Render inside a <ul>. */
export function DocxRow({ downloading, downloadDisabled, onDownload, editHref = null }: DocxRowProps) {
  return (
    <li className="flex flex-col gap-2 rounded-md border border-slate-200 p-3 sm:flex-row sm:items-center sm:justify-between">
      <span className="flex min-w-0 items-center gap-2 text-sm text-slate-700">
        <FileText className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
        Word document (DOCX)
      </span>
      <div className="flex flex-col gap-2 sm:flex-row sm:shrink-0">
        {editHref && (
          <Button asChild variant="outline" size="sm" className="w-full sm:w-auto">
            <Link to={editHref}>
              <FilePenLine className="h-4 w-4" aria-hidden="true" />
              Edit Word file
            </Link>
          </Button>
        )}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onDownload}
          disabled={downloadDisabled}
          className="w-full shrink-0 sm:w-auto"
        >
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Download DOCX
        </Button>
      </div>
    </li>
  );
}

export interface PdfRowProps {
  /** The PDF fields of the generated document (GeneratedInfo, or the preview's mapped state). */
  generated: PdfState | null;
  generating: boolean;
  retrying: boolean;
  downloading: boolean;
  downloadDisabled: boolean;
  retryDisabled: boolean;
  onDownload: () => void;
  onRetry: () => void;
}

/** The PDF file row: its own status, independent of the DOCX (shared with the preview page). */
export function PdfRow({
  generated,
  generating,
  retrying,
  downloading,
  downloadDisabled,
  retryDisabled,
  onDownload,
  onRetry,
}: PdfRowProps) {
  const view = pdfRowView(generated, { generating, retrying });
  if (view.kind === "none") return null;
  const busy = view.kind === "converting" || view.kind === "retrying";

  return (
    <li
      className={`flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between ${
        view.warn ? "border-amber-200 bg-amber-50" : "border-slate-200"
      }`}
    >
      <div className="min-w-0 space-y-1">
        <div aria-live="polite" className="space-y-1">
          <p
            className={`flex items-center gap-2 text-sm ${
              view.warn ? "font-medium text-amber-800" : view.kind === "converted" ? "text-emerald-700" : "text-slate-700"
            }`}
          >
            {busy ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-slate-500" aria-hidden="true" />
            ) : view.warn ? (
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
            ) : (
              <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" aria-hidden="true" />
            )}
            {view.text}
          </p>
          {view.detail && <p className="break-words text-xs text-slate-600">{view.detail}</p>}
        </div>
        {view.filename && (
          <p className="truncate text-xs text-slate-500" title={view.filename}>
            {view.filename}
          </p>
        )}
        {view.earlierPdf && <p className="text-xs text-slate-500">{EARLIER_PDF_NOTE}</p>}
      </div>
      {(view.showRetry || view.showDownload) && (
        <div className="flex flex-col gap-2 sm:flex-row sm:shrink-0">
          {view.showRetry && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onRetry}
              disabled={retryDisabled}
              className="w-full sm:w-auto"
            >
              <RotateCw className="h-4 w-4" aria-hidden="true" />
              Retry PDF
            </Button>
          )}
          {view.showDownload && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onDownload}
              disabled={downloadDisabled}
              className="w-full sm:w-auto"
            >
              {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Download PDF
            </Button>
          )}
        </div>
      )}
    </li>
  );
}
