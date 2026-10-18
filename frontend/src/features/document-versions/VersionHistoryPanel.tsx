import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { Download, Eye, History, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { useDocumentVersions, useDownloadVersion, useRestoreVersion } from "@/hooks/queries";
import { ApiError, type Document, type DocumentVersion } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import {
  changedFieldsText,
  restoreConfirmText,
  restoreErrorMessage,
  versionDownloadErrorMessage,
  versionDownloadState,
  versionLabel,
  versionMeta,
  versionPdfLabel,
  type VersionFormat,
} from "./version-model";

interface VersionHistoryPanelProps {
  documentId: number;
  documentName: string | null;
  /** Field label for a field name (changed fields list). */
  labelOf?: (fieldName: string) => string;
  /** The document is editable (restore allowed). */
  canRestore: boolean;
  /** Called with the restored document (the edit page reloads its form). */
  onRestored?: (document: Document) => void;
  /** Extra guard before restoring, e.g. a busy form. */
  restoreDisabled?: boolean;
  /** Card title level / framing: "card" (own card) or "plain" (inside a section). */
  variant?: "card" | "plain";
  className?: string;
}

function relativeTime(value: string): string {
  const date = parseServerDate(value);
  return date ? formatDistanceToNow(date, { addSuffix: true }) : "";
}

/**
 * Every generated version of a document (newest first): who generated it and
 * when, what changed, the PDF state, per-version DOCX / PDF downloads
 * (disabled with the reason once retention removed the files), a link to
 * the read-only version view, and Restore (copies the version's values into
 * the draft after a confirmation).
 */
export function VersionHistoryPanel({
  documentId,
  documentName,
  labelOf = (name) => name,
  canRestore,
  onRestored,
  restoreDisabled = false,
  variant = "card",
  className,
}: VersionHistoryPanelProps) {
  const versionsQuery = useDocumentVersions(documentId);
  const download = useDownloadVersion();
  const restore = useRestoreVersion();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<DocumentVersion | null>(null);

  const handleDownload = async (version: DocumentVersion, format: VersionFormat) => {
    const key = `${version.version}-${format}`;
    setDownloading(key);
    try {
      await download.mutateAsync({ documentId, version: version.version, format, name: documentName });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      toast({
        variant: "destructive",
        title: `Couldn't download ${versionLabel(version)} ${format.toUpperCase()}`,
        description: versionDownloadErrorMessage(status, format, err instanceof Error ? err.message : undefined),
      });
      if (status === 404 || status === 409 || status === 410) void versionsQuery.refetch();
    } finally {
      setDownloading(null);
    }
  };

  const handleRestore = async () => {
    const version = confirming;
    if (!version) return;
    try {
      const document = await restore.mutateAsync({ documentId, version: version.version });
      setConfirming(null);
      toast({
        title: `Restored the values of ${versionLabel(version)}`,
        description: "Generate to create a new version from them.",
        duration: 4000,
      });
      onRestored?.(document);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      setConfirming(null);
      toast({
        variant: "destructive",
        title: "Restore failed",
        description: restoreErrorMessage(status, err instanceof Error ? err.message : undefined),
      });
    }
  };

  const versions = versionsQuery.data ?? [];
  const body = (() => {
    if (versionsQuery.isPending) {
      return (
        <div className="space-y-3" aria-busy="true" aria-label="Loading versions">
          <Skeleton className="h-16 bg-slate-100" />
          <Skeleton className="h-16 bg-slate-100" />
        </div>
      );
    }
    if (versionsQuery.isError) {
      return (
        <div className="space-y-2 text-sm">
          <p className="text-red-600">{versionsQuery.error.message || "Couldn't load the versions."}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void versionsQuery.refetch()}>
            Try again
          </Button>
        </div>
      );
    }
    if (versions.length === 0) {
      return <p className="text-sm text-slate-500">No versions yet. Generate the document to create version 1.</p>;
    }
    return (
      <ol className="divide-y divide-slate-100" aria-label="Versions, newest first">
        {versions.map((version) => {
          const docx = versionDownloadState(version, "docx");
          const pdf = versionDownloadState(version, "pdf");
          return (
            <li key={version.version} className="space-y-1.5 py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-sm font-medium text-slate-900">
                  <span title={parseServerDate(version.created_at)?.toLocaleString()}>
                    {versionMeta(version, relativeTime(version.created_at))}
                  </span>
                </p>
                {version.is_latest && (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                    Latest
                  </span>
                )}
              </div>
              <p className="break-words text-xs text-slate-600">{changedFieldsText(version, labelOf)}</p>
              <p
                className={cn(
                  "text-xs",
                  version.files_pruned ? "text-amber-700" : version.has_pdf ? "text-slate-500" : "text-amber-700",
                )}
              >
                {version.files_pruned ? `${versionPdfLabel(version)} · retention` : versionPdfLabel(version)}
              </p>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {(["docx", "pdf"] as const).map((format) => {
                  const state = format === "docx" ? docx : pdf;
                  const busy = downloading === `${version.version}-${format}`;
                  return (
                    <Button
                      key={format}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      disabled={!state.enabled || busy}
                      title={state.reason ?? `Download ${versionLabel(version)} as ${format.toUpperCase()}`}
                      aria-label={`Download ${versionLabel(version)} ${format.toUpperCase()}${state.reason ? ` (${state.reason})` : ""}`}
                      onClick={() => void handleDownload(version, format)}
                    >
                      {busy ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <Download className="h-3.5 w-3.5" aria-hidden="true" />
                      )}
                      {format.toUpperCase()}
                    </Button>
                  );
                })}
                <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
                  <Link to={`/documents/${documentId}/versions/${version.version}`}>
                    <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                    View<span className="sr-only"> {versionLabel(version)}</span>
                  </Link>
                </Button>
                {canRestore && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    disabled={restoreDisabled || restore.isPending}
                    onClick={() => setConfirming(version)}
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                    Restore<span className="sr-only"> {versionLabel(version)}</span>
                  </Button>
                )}
              </div>
              {version.files_pruned && (
                <p className="text-[11px] leading-snug text-slate-500">
                  Files removed by retention. View or restore its values, then generate again.
                </p>
              )}
            </li>
          );
        })}
      </ol>
    );
  })();

  const dialog = (
    <Dialog open={confirming !== null} onOpenChange={(open) => !open && !restore.isPending && setConfirming(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Restore {confirming ? versionLabel(confirming) : "version"}?</DialogTitle>
          <DialogDescription>{confirming ? restoreConfirmText(confirming) : ""}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setConfirming(null)} disabled={restore.isPending}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void handleRestore()} disabled={restore.isPending}>
            {restore.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            Restore values
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (variant === "plain") {
    return (
      <div className={className}>
        {body}
        {dialog}
      </div>
    );
  }
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-slate-500" aria-hidden="true" />
          Version history
          {versions.length > 0 && <span className="text-sm font-normal text-slate-500">({versions.length})</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">{body}</CardContent>
      {dialog}
    </Card>
  );
}
