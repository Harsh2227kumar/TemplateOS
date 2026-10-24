import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, ChevronLeft, Download, FilePenLine, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { PreviewSectionCard } from "@/features/document-preview/PreviewSectionCard";
import { previewTitle } from "@/features/document-preview/preview-model";
import {
  changedFieldsText,
  manualEditLabel,
  PRUNED_DETAIL,
  restoreConfirmText,
  restoreErrorMessage,
  versionDownloadErrorMessage,
  versionDownloadState,
  versionLabel,
  versionPdfLabel,
  type VersionFormat,
} from "@/features/document-versions/version-model";
import { DraftLoadError, DraftNotFound } from "@/features/documents/DraftLoadStates";
import { useNow } from "@/features/documents/use-draft-form";
import { canEditDocumentFile, documentEditorPath, VALUES_UNCHANGED_NOTE } from "@/features/word-editor/word-editor-model";
import { useDocument, useDocumentVersion, useDownloadVersion, useEditorEnabled, useRestoreVersion } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";
import { parseRouteId } from "@/lib/route-params";

// Same rule as the backend (document_permissions.EDITABLE_STATUSES).
const EDITABLE_STATUSES = ["draft", "generated"];

/** V1.7 P2: one generated version, read-only, at /documents/:id/versions/:version. */
export function DocumentVersionPage() {
  const navigate = useNavigate();
  const params = useParams<{ id: string; version: string }>();
  const documentId = parseRouteId(params.id) ?? 0;
  const versionNumber = parseRouteId(params.version) ?? 0;
  const versionQuery = useDocumentVersion(documentId, versionNumber);
  const documentQuery = useDocument(documentId);
  const download = useDownloadVersion();
  const restore = useRestoreVersion();
  const editorEnabled = useEditorEnabled();
  const [downloading, setDownloading] = useState<VersionFormat | null>(null);
  const [confirming, setConfirming] = useState(false);
  useNow();

  const version = versionQuery.data ?? null;
  const document = documentQuery.data ?? null;
  const canRestore = !!document && EDITABLE_STATUSES.includes(document.status);

  if (!documentId || !versionNumber) {
    return <DraftNotFound title="Version not found" description="This link is not valid." backTo="/" backLabel="Go to Dashboard" />;
  }

  if (versionQuery.isPending) {
    return (
      <div className="mx-auto max-w-4xl space-y-6" aria-busy="true" aria-label="Loading the version">
        <Skeleton className="h-8 w-2/3 bg-slate-100" />
        <Skeleton className="h-64 bg-slate-100" />
      </div>
    );
  }

  if (versionQuery.isError || !version) {
    const status = versionQuery.error?.status;
    if (status === 404 || status === 403 || !version) {
      return (
        <DraftNotFound
          title="Version not found"
          description="This version doesn't exist or you don't have access to it."
          backTo={`/documents/${documentId}/preview`}
          backLabel="Back to the preview"
        />
      );
    }
    return (
      <DraftLoadError
        title="Couldn't load this version"
        message={versionQuery.error?.message || "Please try again."}
        onRetry={() => void versionQuery.refetch()}
        backTo={`/documents/${documentId}/preview`}
        backLabel="Back to the preview"
      />
    );
  }

  const created = parseServerDate(version.created_at);
  const name = previewTitle(document?.name ?? null);
  const manualLabel = manualEditLabel(version);
  const canEditFile = canEditDocumentFile({
    editorEnabled,
    documentStatus: document?.status,
    hasDocx: versionDownloadState(version, "docx").enabled,
  });

  const handleDownload = async (format: VersionFormat) => {
    setDownloading(format);
    try {
      await download.mutateAsync({ documentId, version: version.version, format, name: document?.name });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      toast({
        variant: "destructive",
        title: `Couldn't download the ${format.toUpperCase()}`,
        description: versionDownloadErrorMessage(status, format, err instanceof Error ? err.message : undefined),
      });
      if (status === 409 || status === 410) void versionQuery.refetch();
    } finally {
      setDownloading(null);
    }
  };

  const handleRestore = async () => {
    try {
      await restore.mutateAsync({ documentId, version: version.version });
      setConfirming(false);
      toast({
        title: `Restored the values of ${versionLabel(version)}`,
        description: "Review them, then generate to create a new version.",
        duration: 4000,
      });
      navigate(`/documents/${documentId}/edit`);
    } catch (err) {
      setConfirming(false);
      toast({
        variant: "destructive",
        title: "Restore failed",
        description: restoreErrorMessage(err instanceof ApiError ? err.status : undefined, err instanceof Error ? err.message : undefined),
      });
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-3">
        <Button variant="ghost" size="sm" asChild className="-ml-2 h-8 px-2 text-slate-600">
          <Link to={`/documents/${documentId}/preview`}>
            <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
            Preview
          </Link>
        </Button>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="break-words text-2xl font-bold text-slate-900">
              {name} <span className="font-semibold text-slate-500">· {versionLabel(version)}</span>
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Generated{" "}
              <span title={created?.toLocaleString()}>{created ? formatDistanceToNow(created, { addSuffix: true }) : ""}</span>{" "}
              by {version.created_by_name}
              {version.template_version ? ` · template v${version.template_version}` : ""} · {versionPdfLabel(version)}
              {version.is_latest && (
                <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                  Latest
                </span>
              )}
              {manualLabel && (
                <span className="ml-2 rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700">
                  {manualLabel}
                </span>
              )}
            </p>
            <p className="mt-1 text-sm text-slate-600">{changedFieldsText(version)}</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {(["docx", "pdf"] as const).map((format) => {
              const state = versionDownloadState(version, format);
              return (
                <Button
                  key={format}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!state.enabled || downloading !== null}
                  title={state.reason ?? undefined}
                  onClick={() => void handleDownload(format)}
                >
                  {downloading === format ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Download className="h-4 w-4" aria-hidden="true" />
                  )}
                  {format.toUpperCase()}
                  {state.reason && <span className="sr-only"> ({state.reason})</span>}
                </Button>
              );
            })}
            {canEditFile && (
              <Button asChild type="button" variant="outline" size="sm">
                <Link to={documentEditorPath(documentId, version.version)}>
                  <FilePenLine className="h-4 w-4" aria-hidden="true" />
                  Edit Word file
                </Link>
              </Button>
            )}
            {canRestore && (
              <Button type="button" size="sm" onClick={() => setConfirming(true)} disabled={restore.isPending}>
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Restore these values
              </Button>
            )}
          </div>
        </div>
      </div>

      {version.files_pruned && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {PRUNED_DETAIL}
        </div>
      )}

      <p className="text-xs text-slate-500">
        Read-only: these are the values this version was generated from.
        {manualLabel && ` ${VALUES_UNCHANGED_NOTE}`}
      </p>

      {version.sections.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
          This version has no values.
        </p>
      ) : (
        version.sections.map((section, index) => <PreviewSectionCard key={`${section.name}-${index}`} section={section} />)
      )}

      <Dialog open={confirming} onOpenChange={(open) => !restore.isPending && setConfirming(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore {versionLabel(version)}?</DialogTitle>
            <DialogDescription>{restoreConfirmText(version)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirming(false)} disabled={restore.isPending}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void handleRestore()} disabled={restore.isPending}>
              {restore.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              Restore values
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
