import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, Eye, EyeOff, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PDF_FILE_MISSING_MESSAGE } from "@/features/documents/generation";
import { ApiError, documentsApi } from "@/lib/api";

/** Tailwind's `sm` breakpoint: below it the PDF opens in a new tab instead of an iframe. */
const WIDE_QUERY = "(min-width: 640px)";

function useMatchMedia(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : true,
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

type PdfBlobState =
  | { status: "loading" }
  | { status: "ready"; url: string }
  | { status: "error"; message: string; fileMissing: boolean };

/**
 * Fetch the generated PDF as a blob with the session cookies (the same
 * requestFile helper as downloads) and expose it as an object URL. The URL
 * is revoked when the component unmounts, the preview closes, or the PDF
 * changes (`pdfKey`, which includes generated_at).
 */
function usePdfBlobUrl(documentId: number, pdfKey: string | null, enabled: boolean, attempt: number) {
  const [state, setState] = useState<PdfBlobState>({ status: "loading" });

  useEffect(() => {
    if (!enabled || !pdfKey) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setState({ status: "loading" });
    documentsApi
      .download(documentId, "pdf")
      .then((file) => {
        if (cancelled) return;
        const blob = file.blob.type === "application/pdf" ? file.blob : new Blob([file.blob], { type: "application/pdf" });
        objectUrl = URL.createObjectURL(blob);
        setState({ status: "ready", url: objectUrl });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const fileMissing = err instanceof ApiError && err.status === 410;
        setState({
          status: "error",
          fileMissing,
          message: fileMissing
            ? PDF_FILE_MISSING_MESSAGE
            : err instanceof Error && err.message
              ? err.message
              : "Couldn't load the PDF. Please try again.",
        });
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      // Never render a revoked URL when the preview reopens or the PDF changes.
      setState({ status: "loading" });
    };
  }, [documentId, pdfKey, enabled, attempt]);

  return state;
}

interface PdfPreviewToggleProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** "Preview PDF" / "Hide PDF preview" (render only when the PDF exists). */
export function PdfPreviewToggle({ open, onOpenChange }: PdfPreviewToggleProps) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => onOpenChange(!open)}
      aria-expanded={open}
      aria-controls="pdf-preview"
      className="w-full sm:w-auto"
    >
      {open ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
      {open ? "Hide PDF preview" : "Preview PDF"}
    </Button>
  );
}

interface PdfPreviewProps {
  documentId: number;
  /** From pdfPreviewKey(): null when there is no PDF. */
  pdfKey: string | null;
  documentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The server no longer has the PDF file (410): refresh the preview data. */
  onFileMissing?: () => void;
}

/** Collapsible inline preview of the real generated PDF (the browser's own viewer). */
export function PdfPreview({ documentId, pdfKey, documentName, open, onOpenChange, onFileMissing }: PdfPreviewProps) {
  const [attempt, setAttempt] = useState(0);
  const wide = useMatchMedia(WIDE_QUERY);
  const active = open && pdfKey !== null;
  const state = usePdfBlobUrl(documentId, pdfKey, active, attempt);
  const fileMissing = state.status === "error" && state.fileMissing;

  useEffect(() => {
    if (active && fileMissing) onFileMissing?.();
  }, [active, fileMissing, onFileMissing]);

  if (!active) return null;

  return (
    <Card id="pdf-preview">
      <CardContent className="space-y-3 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">PDF preview</h2>
          <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            <EyeOff className="h-4 w-4" aria-hidden="true" />
            Hide
          </Button>
        </div>

        {state.status === "loading" && (
          <div aria-busy="true" aria-label="Loading the PDF">
            {wide ? <Skeleton className="h-[70vh] w-full rounded" /> : <Skeleton className="h-10 w-full rounded" />}
          </div>
        )}

        {state.status === "error" && (
          <div className="flex flex-col gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 sm:flex-row sm:items-center sm:justify-between" role="alert">
            <p className="flex items-start gap-2 break-words text-sm text-amber-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
              {state.message}
            </p>
            {!state.fileMissing && (
              <Button type="button" size="sm" variant="outline" onClick={() => setAttempt((n) => n + 1)} className="w-full shrink-0 sm:w-auto">
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Retry
              </Button>
            )}
          </div>
        )}

        {state.status === "ready" &&
          (wide ? (
            <iframe title={`PDF preview of ${documentName}`} src={state.url} className="h-[70vh] w-full rounded border" />
          ) : (
            <Button asChild className="w-full">
              <a href={state.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                Open PDF
              </a>
            </Button>
          ))}
      </CardContent>
    </Card>
  );
}
