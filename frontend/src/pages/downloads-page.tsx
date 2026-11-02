import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { Download } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { DownloadButton } from "@/features/downloads/DownloadButton";
import { downloadDocumentName, humanFileSize } from "@/features/downloads/history-model";
import { useMyDocuments, useMyDownloads } from "@/hooks/queries";
import type { DownloadHistoryItem } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";

const PAGE_SIZE = 20;
const ALL = "all";

function When({ value }: { value: string }) {
  const date = parseServerDate(value);
  return <span title={date?.toLocaleString()}>{date ? formatDistanceToNow(date, { addSuffix: true }) : ""}</span>;
}

function DocumentCell({ item }: { item: DownloadHistoryItem }) {
  if (!item.document_exists || item.document_id === null) {
    return <span className="text-slate-500">{downloadDocumentName(item)}</span>;
  }
  return (
    <Link to={`/documents/${item.document_id}/preview`} className="font-medium text-slate-900 hover:underline">
      {item.document_name}
    </Link>
  );
}

function VersionCell({ item }: { item: DownloadHistoryItem }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {item.version ? `v${item.version}` : "—"}
      {item.version_source === "manual_edit" && (
        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700">
          Edited manually
        </span>
      )}
    </span>
  );
}

function FormatBadge({ format }: { format: string }) {
  return (
    <Badge variant="outline" className={format === "pdf" ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-700"}>
      {format.toUpperCase()}
    </Badge>
  );
}

function AgainButton({ item }: { item: DownloadHistoryItem }) {
  if (!item.document_exists || item.document_id === null) return null;
  return (
    <DownloadButton
      documentId={item.document_id}
      format={item.format}
      version={item.version}
      name={item.document_name}
      label="Download again"
      variant="ghost"
      className="h-8 px-2 text-xs"
    />
  );
}

/** V1.7 P3: every file you downloaded, newest first. */
export function DownloadsPage() {
  const [page, setPage] = useState(1);
  const [format, setFormat] = useState<string>(ALL);
  const [documentId, setDocumentId] = useState<string>(ALL);
  const documents = useMyDocuments();
  const downloads = useMyDownloads({
    page,
    limit: PAGE_SIZE,
    format: format === ALL ? undefined : (format as "docx" | "pdf"),
    document_id: documentId === ALL ? undefined : Number(documentId),
  });
  const items = downloads.data?.items ?? [];
  const total = downloads.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = format !== ALL || documentId !== ALL;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Downloads</h1>
        <p className="mt-1 text-sm text-slate-600">Every Word and PDF file you downloaded.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-xl">
        <Select value={format} onValueChange={(value) => { setFormat(value); setPage(1); }}>
          <SelectTrigger aria-label="Filter by format">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All formats</SelectItem>
            <SelectItem value="docx">Word (DOCX)</SelectItem>
            <SelectItem value="pdf">PDF</SelectItem>
          </SelectContent>
        </Select>
        <Select value={documentId} onValueChange={(value) => { setDocumentId(value); setPage(1); }}>
          <SelectTrigger aria-label="Filter by document">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All documents</SelectItem>
            {(documents.data ?? []).map((document) => (
              <SelectItem key={document.id} value={String(document.id)}>
                {document.name || `Draft ${document.id}`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {downloads.isPending ? (
        <div className="space-y-2" aria-busy="true" aria-label="Loading downloads">
          <Skeleton className="h-12 bg-slate-100" />
          <Skeleton className="h-12 bg-slate-100" />
        </div>
      ) : downloads.isError && !downloads.data ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p>{downloads.error.message || "Couldn't load your downloads."}</p>
          <Button variant="outline" size="sm" className="mt-3 bg-white" onClick={() => void downloads.refetch()}>
            Try again
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-200 p-10 text-center">
          <Download className="h-8 w-8 text-slate-300" aria-hidden="true" />
          <p className="mt-3 font-medium text-slate-700">{filtered ? "No downloads match these filters" : "No downloads yet"}</p>
          <p className="mt-1 text-sm text-slate-500">Files you download from a document appear here.</p>
        </div>
      ) : (
        <>
          {/* Cards below 640 px, a table above. */}
          <ul className="space-y-3 sm:hidden" aria-label="Downloads">
            {items.map((item) => (
              <li key={item.id} className="space-y-1.5 rounded-lg border border-slate-200 bg-white p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <DocumentCell item={item} />
                  <FormatBadge format={item.format} />
                </div>
                <p className="text-xs text-slate-500">
                  <When value={item.downloaded_at} /> · <VersionCell item={item} />
                  {item.file_size ? ` · ${humanFileSize(item.file_size)}` : ""}
                </p>
                <p className="truncate text-xs text-slate-500" title={item.file_name}>{item.file_name}</p>
                <AgainButton item={item} />
              </li>
            ))}
          </ul>
          <div className="hidden overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm sm:block">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3">When</th>
                    <th className="px-4 py-3">Document</th>
                    <th className="px-4 py-3">Version</th>
                    <th className="px-4 py-3">Format</th>
                    <th className="px-4 py-3">File</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((item) => (
                    <tr key={item.id} className="align-middle">
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600"><When value={item.downloaded_at} /></td>
                      <td className="px-4 py-3"><DocumentCell item={item} /></td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600"><VersionCell item={item} /></td>
                      <td className="px-4 py-3"><FormatBadge format={item.format} /></td>
                      <td className="max-w-[16rem] truncate px-4 py-3 text-slate-600" title={item.file_name}>{item.file_name}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{humanFileSize(item.file_size) || "—"}</td>
                      <td className="px-4 py-3 text-right"><AgainButton item={item} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between text-sm text-slate-600">
              <span>Page {page} of {pageCount} · {total} download{total === 1 ? "" : "s"}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
