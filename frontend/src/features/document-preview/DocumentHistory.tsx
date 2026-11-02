import { useState, type ComponentProps } from "react";
import { formatDistanceToNow } from "date-fns";
import { Download, History } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { VersionHistoryPanel } from "@/features/document-versions/VersionHistoryPanel";
import { downloadLabel, humanFileSize } from "@/features/downloads/history-model";
import { useDocumentDownloads } from "@/hooks/queries";
import { parseServerDate } from "@/lib/dates";
import { cn } from "@/lib/utils";

const PAGE = 10;

type Tab = "versions" | "downloads";

function DocumentDownloads({ documentId }: { documentId: number }) {
  const [limit, setLimit] = useState(PAGE);
  const downloads = useDocumentDownloads(documentId, { page: 1, limit });

  if (downloads.isPending) return <Skeleton className="h-16 bg-slate-100" aria-label="Loading downloads" />;
  if (downloads.isError) {
    return <p className="text-sm text-red-600">{downloads.error.message || "Couldn't load the downloads."}</p>;
  }
  const { items, total } = downloads.data;
  if (items.length === 0) return <p className="text-sm text-slate-500">Not downloaded yet.</p>;
  return (
    <div className="space-y-3">
      <ol className="divide-y divide-slate-100" aria-label="Downloads, newest first">
        {items.map((item) => {
          const when = parseServerDate(item.downloaded_at);
          return (
            <li key={item.id} className="flex items-start gap-2 py-2 first:pt-0 last:pb-0 text-sm">
              <Download className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-slate-800">{downloadLabel(item)}</p>
                <p className="text-xs text-slate-500">
                  <span title={when?.toLocaleString()}>{when ? formatDistanceToNow(when, { addSuffix: true }) : ""}</span>
                  {item.file_size ? ` · ${humanFileSize(item.file_size)}` : ""}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
      {items.length < total && limit < 100 && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          disabled={downloads.isFetching}
          onClick={() => setLimit((current) => Math.min(100, current + PAGE))}
        >
          Show more ({total - items.length})
        </Button>
      )}
    </div>
  );
}

/**
 * V1.7 P3: the document's history on the preview page: its versions (P2,
 * with P2.1 "Edited manually" and "Edit Word file") and its downloads.
 */
export function DocumentHistory(props: ComponentProps<typeof VersionHistoryPanel>) {
  const [tab, setTab] = useState<Tab>("versions");
  const tabs: { id: Tab; label: string }[] = [
    { id: "versions", label: "Versions" },
    { id: "downloads", label: "Downloads" },
  ];
  return (
    <Card className={props.className}>
      <CardHeader className="space-y-3 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-slate-500" aria-hidden="true" />
          History
        </CardTitle>
        <div role="tablist" aria-label="Document history" className="flex gap-1 rounded-lg bg-slate-100 p-1">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`history-tab-${item.id}`}
              aria-selected={tab === item.id}
              aria-controls={`history-panel-${item.id}`}
              onClick={() => setTab(item.id)}
              className={cn(
                "flex-1 rounded-md px-3 py-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                tab === item.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div role="tabpanel" id={`history-panel-${tab}`} aria-labelledby={`history-tab-${tab}`}>
          {tab === "versions" ? (
            <VersionHistoryPanel {...props} variant="plain" className={undefined} />
          ) : (
            <DocumentDownloads documentId={props.documentId} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
