import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { CompletenessCard } from "@/features/document-preview/CompletenessCard";
import { GeneratedDocumentCard } from "@/features/document-preview/GeneratedDocumentCard";
import { PdfPreview } from "@/features/document-preview/PdfPreview";
import { PreviewHeader } from "@/features/document-preview/PreviewHeader";
import { PreviewSectionCard } from "@/features/document-preview/PreviewSectionCard";
import { LazyVersionHistoryPanel } from "@/features/document-versions/LazyVersionHistoryPanel";
import { pdfPreviewKey, previewTitle } from "@/features/document-preview/preview-model";
import { DraftLoadError, DraftNotFound } from "@/features/documents/DraftLoadStates";
import {
  generateSuccessMessage,
  versionCreatedText,
  PDF_FILE_MISSING_MESSAGE,
  RETRY_DOCX_MISSING_MESSAGE,
  type DownloadFormat,
} from "@/features/documents/generation";
import { useNow } from "@/features/documents/use-draft-form";
import {
  canEditDocumentFile,
  documentEditorPath,
  manualEditsConflict,
  type ManualEditsConflict,
} from "@/features/word-editor/word-editor-model";
import {
  useDocumentPreview,
  useDownloadGenerated,
  useEditorEnabled,
  useGenerateDocument,
  useRetryPdf,
} from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { parseRouteId } from "@/lib/route-params";

// V1.7 P2.1: loaded when generate asks about manual edits.
const ManualEditsDialog = lazy(() =>
  import("@/features/word-editor/ManualEditsDialog").then((module) => ({ default: module.ManualEditsDialog })),
);

function PreviewLoadingSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading the preview">
      <div className="space-y-2">
        <Skeleton className="h-8 w-2/3 bg-slate-100" />
        <Skeleton className="h-4 w-1/2 bg-slate-100" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Skeleton className="h-64 bg-slate-100" />
          <Skeleton className="h-40 bg-slate-100" />
        </div>
        <div className="space-y-6">
          <Skeleton className="h-32 bg-slate-100" />
          <Skeleton className="h-48 bg-slate-100" />
        </div>
      </div>
    </div>
  );
}

const NOT_FOUND = (
  <DraftNotFound
    title="Document not found"
    description="The draft you're looking for doesn't exist or you don't have access to it."
    backTo="/"
    backLabel="Go to Dashboard"
  />
);

/** V1.7: read-only "is my document ready?" page at /documents/:id/preview. */
export function DocumentPreviewPage() {
  const { id: documentIdParam } = useParams<{ id: string }>();
  const documentId = parseRouteId(documentIdParam) ?? 0;
  const previewQuery = useDocumentPreview(documentId);
  const generateDocument = useGenerateDocument();
  const retryPdf = useRetryPdf();
  const downloadGenerated = useDownloadGenerated();
  const [downloading, setDownloading] = useState<DownloadFormat | null>(null);
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [manualConflict, setManualConflict] = useState<ManualEditsConflict | null>(null);
  const editorEnabled = useEditorEnabled();
  useNow();

  const preview = previewQuery.data ?? null;
  const pdfKey = pdfPreviewKey(documentId, preview?.generation);
  const { refetch } = previewQuery;
  const refreshPreview = useCallback(() => void refetch(), [refetch]);

  // No PDF any more (regenerating, file removed): close the inline preview.
  useEffect(() => {
    if (pdfKey === null) setPdfPreviewOpen(false);
  }, [pdfKey]);

  if (!documentId) return NOT_FOUND;

  const handleGenerate = async (replaceManualEdits = false) => {
    if (generateDocument.isPending || retryPdf.isPending) return;
    try {
      const result = await generateDocument.mutateAsync({ documentId, replaceManualEdits });
      setManualConflict(null);
      toast({
        title: versionCreatedText(result) ?? generateSuccessMessage(result.pdf_status),
        description: versionCreatedText(result) ? generateSuccessMessage(result.pdf_status) : undefined,
        duration: 3500,
      });
    } catch (err) {
      const conflict = manualEditsConflict(err);
      if (conflict) {
        setManualConflict(conflict);
        return;
      }
      setManualConflict(null);
      const status = err instanceof ApiError ? err.status : undefined;
      toast({
        variant: "destructive",
        title: status === 422 ? "Some fields need attention" : "Failed to generate the document",
        description:
          status === 422
            ? "Edit the draft to fix the highlighted fields, then generate again."
            : err instanceof Error && err.message
              ? err.message
              : "Please try again.",
      });
    }
  };

  const handleRetryPdf = async () => {
    if (generateDocument.isPending || retryPdf.isPending) return;
    try {
      await retryPdf.mutateAsync(documentId);
      toast({ title: "PDF ready", duration: 2500 });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      // 503: the server recorded the reason; the refetched PDF row shows it in amber.
      if (status === 503) return;
      toast({
        variant: "destructive",
        title: "Retry failed",
        description:
          status === 410
            ? RETRY_DOCX_MISSING_MESSAGE
            : err instanceof Error && err.message
              ? err.message
              : "Please try again.",
      });
    }
  };

  const handleDownload = async (format: DownloadFormat) => {
    setDownloading(format);
    try {
      await downloadGenerated.mutateAsync({ documentId, format, name: preview?.document.name });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      toast({
        variant: "destructive",
        title: status === 409 && format === "pdf" ? "PDF not available" : "Download failed",
        description:
          format === "pdf" && status === 410
            ? PDF_FILE_MISSING_MESSAGE
            : err instanceof Error
              ? err.message
              : undefined,
      });
      // The server state differs from what we show (file removed, not generated).
      if (status === 404 || status === 409 || status === 410) refreshPreview();
    } finally {
      setDownloading(null);
    }
  };

  if (previewQuery.isPending) return <PreviewLoadingSkeleton />;

  if (previewQuery.isError && !preview) {
    const error = previewQuery.error;
    if (error.status === 404 || error.status === 403) return NOT_FOUND;
    return (
      <DraftLoadError
        title="Couldn't load the preview"
        message={error.message || "Failed to load the preview. Please try again."}
        onRetry={refreshPreview}
        backTo="/"
        backLabel="Go to Dashboard"
      />
    );
  }

  if (!preview) return NOT_FOUND;

  const generating = generateDocument.isPending;
  const retrying = retryPdf.isPending;
  const editFileHref = canEditDocumentFile({
    editorEnabled,
    documentStatus: preview.permissions.can_edit ? preview.document.status : null,
    hasDocx: Boolean(preview.generation?.docx_available),
  })
    ? documentEditorPath(documentId)
    : null;
  const labels = new Map(preview.sections.flatMap((section) => section.fields.map((f) => [f.field_name, f.label] as const)));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PreviewHeader
        preview={preview}
        generating={generating}
        busy={retrying}
        onGenerate={() => void handleGenerate()}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <div className="order-2 min-w-0 space-y-6 lg:order-1">
          <PdfPreview
            documentId={documentId}
            pdfKey={pdfKey}
            documentName={previewTitle(preview.document.name)}
            open={pdfPreviewOpen}
            onOpenChange={setPdfPreviewOpen}
            onFileMissing={refreshPreview}
          />
          {preview.sections.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
              This template has no fields.
            </p>
          ) : (
            preview.sections.map((section, index) => (
              <PreviewSectionCard key={`${section.name}-${index}`} section={section} />
            ))
          )}
        </div>

        <aside className="order-1 min-w-0 space-y-6 lg:sticky lg:top-6 lg:order-2" aria-label="Document status">
          <CompletenessCard preview={preview} />
          <GeneratedDocumentCard
            preview={preview}
            generating={generating}
            retryingPdf={retrying}
            downloading={downloading}
            onGenerate={() => void handleGenerate()}
            onRetryPdf={() => void handleRetryPdf()}
            onDownload={(format) => void handleDownload(format)}
            pdfPreviewOpen={pdfPreviewOpen}
            onPdfPreviewOpenChange={setPdfPreviewOpen}
            editFileHref={editFileHref}
          />
          {preview.generation && (
            <LazyVersionHistoryPanel
              documentId={documentId}
              documentName={preview.document.name}
              labelOf={(name) => labels.get(name) || name}
              canRestore={preview.permissions.can_edit}
              restoreDisabled={generating || retrying}
            />
          )}
        </aside>
      </div>
      {manualConflict && (
        <Suspense fallback={null}>
          <ManualEditsDialog
            conflict={manualConflict}
            generating={generating}
            onCancel={() => setManualConflict(null)}
            onConfirm={() => void handleGenerate(true)}
          />
        </Suspense>
      )}
    </div>
  );
}
