import { lazy, Suspense } from "react";

import type { RichDoc } from "./rich-model";

const RichTextViewerContent = lazy(() => import("./RichTextViewerContent"));

/**
 * Read-only rich text (preview page, version view). Until the viewer chunk
 * loads, the plain text the generated document shows is displayed.
 */
export function RichTextViewer({ doc, fallbackText, label }: { doc: RichDoc; fallbackText: string; label?: string }) {
  return (
    <Suspense
      fallback={<p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-900">{fallbackText}</p>}
    >
      <RichTextViewerContent doc={doc} label={label} />
    </Suspense>
  );
}
