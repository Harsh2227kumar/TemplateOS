import { useMemo, useRef, useState } from "react";
import { MousePointerClick, Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MonoKey } from "@/components/fields/pipeline-ui";
import type { DocSegment, TemplateContent } from "@/lib/api";
import { fieldTypeLabel } from "@/lib/template-pipeline";

import { LOCATION_LABEL, LOCATION_ORDER, MAX_SELECTION, type ConvertValues } from "./cleaning-model";
import { ConvertSelectionDialog } from "./ConvertSelectionDialog";
import { HighlightedText } from "./HighlightedText";
import type { CleaningSession } from "./use-cleaning-session";

interface ManualPlaceholdersPanelProps {
  content: TemplateContent;
  session: CleaningSession;
}

/** RIGHT column: the document text; select text and convert it into a placeholder. */
export function ManualPlaceholdersPanel({ content, session }: ManualPlaceholdersPanelProps) {
  const { manual } = session;
  const [selectedText, setSelectedText] = useState("");
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [convertOpen, setConvertOpen] = useState(false);
  const documentRef = useRef<HTMLDivElement>(null);

  const segmentsByLocation = useMemo(() => {
    const grouped: Partial<Record<DocSegment["location"], DocSegment[]>> = {};
    for (const segment of content.segments) (grouped[segment.location] ??= []).push(segment);
    return grouped;
  }, [content]);

  const handleSelection = () => {
    if (convertOpen) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    const anchorElement = selection.anchorNode?.parentElement ?? null;
    if (!anchorElement || !documentRef.current?.contains(anchorElement)) return;
    const text = selection.toString().trim();
    if (!text) return;
    if (text.length > MAX_SELECTION) {
      setSelectedText("");
      setSelectionNotice(`Select at most ${MAX_SELECTION} characters — that selection was ${text.length}.`);
      return;
    }
    setSelectionNotice(null);
    setSelectedText(text);
  };

  const clearSelection = () => {
    setSelectedText("");
    window.getSelection()?.removeAllRanges();
  };

  const stageManual = (values: ConvertValues): string | null => {
    if (manual.some((r) => r.sample_text === selectedText)) return "This text is already staged";
    session.addManual({
      sample_text: selectedText,
      placeholder_key: values.placeholder_key.trim(),
      field_label: values.field_label?.trim() || undefined,
      field_type: values.field_type,
      section: values.section?.trim() || undefined,
    });
    setConvertOpen(false);
    clearSelection();
    return null;
  };

  return (
    <aside className="min-w-0 space-y-4 lg:sticky lg:top-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <MousePointerClick className="h-5 w-5 text-slate-500" />
            Manual placeholders
          </CardTitle>
          <CardDescription>
            Missed something? Select text below and convert it. Every occurrence is replaced.
          </CardDescription>
          {selectedText ? (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-700" title={selectedText}>
                “{selectedText}”
              </span>
              <Button size="sm" className="h-8 gap-1.5" onClick={() => setConvertOpen(true)}>
                <Plus className="h-3.5 w-3.5" />
                Convert
              </Button>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={clearSelection}>
                <X className="h-4 w-4" />
                <span className="sr-only">Clear selection</span>
              </Button>
            </div>
          ) : (
            selectionNotice && <p className="text-xs text-amber-700">{selectionNotice}</p>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {manual.length > 0 && (
            <ul className="space-y-2">
              {manual.map((item) => (
                <li key={item.id} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-slate-600" title={item.sample_text}>“{item.sample_text}”</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <MonoKey name={item.placeholder_key} />
                      <Badge variant="outline">{fieldTypeLabel(item.field_type ?? "text")}</Badge>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0 text-slate-400 hover:text-red-600"
                    onClick={() => session.removeManual(item.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span className="sr-only">Remove</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div
            ref={documentRef}
            onMouseUp={handleSelection}
            onTouchEnd={handleSelection}
            onKeyUp={handleSelection}
            className="max-h-[55vh] space-y-4 overflow-y-auto rounded-lg border border-slate-100 p-2"
          >
            {content.segments.length === 0 && (
              <p className="p-4 text-center text-sm text-slate-500">This document has no text.</p>
            )}
            {LOCATION_ORDER.filter((location) => segmentsByLocation[location]?.length).map((location) => (
              <div key={location} className="space-y-1">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {LOCATION_LABEL[location]}
                </p>
                {segmentsByLocation[location]!.map((segment) => (
                  <p
                    key={segment.index}
                    className="whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-xs leading-relaxed text-slate-700 hover:bg-slate-50"
                  >
                    <HighlightedText text={segment.text} />
                  </p>
                ))}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <ConvertSelectionDialog
        open={convertOpen}
        onOpenChange={setConvertOpen}
        selectedText={selectedText}
        onSubmit={stageManual}
      />
    </aside>
  );
}
