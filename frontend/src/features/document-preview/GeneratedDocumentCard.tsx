import { formatDistanceToNow } from "date-fns";
import { CheckCircle2, FileOutput, Info, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DocxRow, PdfRow } from "@/features/documents/GenerationPanel";
import {
  generationSummary,
  markPdfFailed,
  PDF_FILE_MISSING_MESSAGE,
  type DownloadFormat,
} from "@/features/documents/generation";
import type { DocumentPreview } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

import { PdfPreviewToggle } from "./PdfPreview";
import { previewPdfState } from "./preview-model";

interface GeneratedDocumentCardProps {
  preview: DocumentPreview;
  generating: boolean;
  retryingPdf: boolean;
  /** Format currently downloading, if any. */
  downloading: DownloadFormat | null;
  onGenerate: () => void;
  onRetryPdf: () => void;
  onDownload: (format: DownloadFormat) => void;
  pdfPreviewOpen: boolean;
  onPdfPreviewOpenChange: (open: boolean) => void;
}

/**
 * The generated DOCX / PDF state on the preview page. Uses the same row
 * components and labels as the edit page's GenerationPanel.
 */
export function GeneratedDocumentCard({
  preview,
  generating,
  retryingPdf,
  downloading,
  onGenerate,
  onRetryPdf,
  onDownload,
  pdfPreviewOpen,
  onPdfPreviewOpenChange,
}: GeneratedDocumentCardProps) {
  const { generation, permissions } = preview;
  const summary = generationSummary(generation, Boolean(generation?.is_stale));
  const generatedDate = parseServerDate(generation?.generated_at);
  const showGenerate = permissions.can_generate && summary.tone !== "ok";
  const busy = generating || retryingPdf;
  // "converted" in the DB but the file is gone from disk: same amber row as a failed download.
  const basePdf = previewPdfState(generation);
  const pdfState =
    basePdf && basePdf.pdf_status === "converted" && !basePdf.has_pdf
      ? markPdfFailed(basePdf, PDF_FILE_MISSING_MESSAGE, { fileMissing: true })
      : basePdf;

  return (
    <Card>
      <CardContent className="space-y-4 p-4 sm:p-5">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FileOutput className="h-4 w-4 text-slate-500" aria-hidden="true" />
            Generated document
          </h2>
          {generation && (
            <p className="text-sm text-slate-600">
              Generated{" "}
              <span title={generatedDate ? generatedDate.toLocaleString() : undefined}>
                {generatedDate ? formatDistanceToNow(generatedDate, { addSuffix: true }) : "earlier"}
              </span>
              {generation.template_version ? ` · template v${generation.template_version}` : null}
            </p>
          )}
        </div>

        <div aria-live="polite">
          {summary.tone === "warn" ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
              <div className="min-w-0 space-y-0.5">
                <p className="text-sm font-medium text-amber-800">{summary.title}</p>
                <p className="text-sm text-amber-800">{summary.detail}</p>
              </div>
            </div>
          ) : summary.tone === "ok" ? (
            <p className="flex items-center gap-2 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              {summary.title}
            </p>
          ) : (
            <div className="space-y-0.5">
              <p className="text-sm font-medium text-slate-700">{summary.title}</p>
              <p className="text-sm text-slate-500">{summary.detail}</p>
            </div>
          )}
        </div>

        {showGenerate && (
          <Button type="button" onClick={onGenerate} disabled={busy} className="w-full">
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating DOCX and PDF…
              </>
            ) : generation ? (
              <>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Regenerate
              </>
            ) : (
              "Generate document"
            )}
          </Button>
        )}

        {permissions.can_download && (generation || generating) && (
          <ul className="space-y-2" aria-label="Generated files">
            {generation?.docx_available && !generating && (
              <DocxRow
                downloading={downloading === "docx"}
                downloadDisabled={downloading !== null}
                onDownload={() => onDownload("docx")}
              />
            )}
            <PdfRow
              generated={pdfState}
              generating={generating}
              retrying={retryingPdf}
              downloading={downloading === "pdf"}
              downloadDisabled={downloading !== null}
              retryDisabled={!permissions.can_generate || busy || !generation?.docx_available}
              onDownload={() => onDownload("pdf")}
              onRetry={onRetryPdf}
            />
          </ul>
        )}

        {generation?.pdf_available && !generating && (
          <PdfPreviewToggle open={pdfPreviewOpen} onOpenChange={onPdfPreviewOpenChange} />
        )}
      </CardContent>
    </Card>
  );
}
