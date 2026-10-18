import { Component, forwardRef, lazy, Suspense, useImperativeHandle, useMemo, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { RichTextEditorHandle } from "./RichTextEditor";
import { docToPlain, isRichValue, normalizeDoc, plainToDoc, richValue, type RichDoc, type RichValue } from "./rich-model";

// Tiptap and its styles load on demand, in their own chunk.
const RichTextEditor = lazy(() => import("./RichTextEditor"));

export interface RichTextFieldProps {
  /** The form value: a RichValue (a plain string is converted). */
  value: unknown;
  onChange: (value: RichValue) => void;
  onBlur?: () => void;
  /** id of the editable element (labels, #field-<name> links, error focus). */
  inputId: string;
  labelId?: string;
  describedBy?: string;
  invalid?: boolean;
  disabled?: boolean;
  /** Read-only while an AI request runs. */
  locked?: boolean;
  required?: boolean;
  placeholder?: string;
  label?: string;
}

export interface RichTextFieldHandle {
  focus: () => void;
}

/** The field's doc whatever the form holds (old plain strings open as paragraphs). */
export function fieldDoc(value: unknown): RichDoc {
  if (isRichValue(value)) return value.doc;
  return plainToDoc(typeof value === "string" ? value : "");
}

/** Shown while the editor chunk loads: the text, read-only, same box. */
function EditorSkeleton({ doc, inputId }: { doc: RichDoc; inputId: string }) {
  const text = docToPlain(doc);
  return (
    <div className="overflow-hidden rounded-md border border-input bg-white" aria-busy="true">
      <div className="flex h-10 items-center gap-1 border-b border-border bg-slate-50 px-2" aria-hidden="true">
        {Array.from({ length: 8 }, (_, index) => (
          <span key={index} className="h-6 w-6 animate-pulse rounded bg-slate-200/80" />
        ))}
      </div>
      <div
        id={inputId}
        tabIndex={-1}
        className="min-h-[88px] whitespace-pre-wrap px-3 py-2 text-sm leading-relaxed text-slate-500"
      >
        {text || "Loading editor…"}
      </div>
    </div>
  );
}

class EditorLoadBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/**
 * Rich text input for long-text (textarea) fields: the trimmed Tiptap Simple
 * Editor, lazy loaded behind a skeleton. Every change is reported as a
 * whitelist-normalized RichValue ({ format: "rich", doc }).
 */
export const RichTextField = forwardRef<RichTextFieldHandle, RichTextFieldProps>(function RichTextField(
  { value, onChange, onBlur, inputId, labelId, describedBy, invalid, disabled, locked, required, placeholder, label },
  ref,
) {
  const editorRef = useRef<RichTextEditorHandle>(null);
  const doc = useMemo(() => fieldDoc(value), [value]);

  useImperativeHandle(
    ref,
    () => ({
      focus: () => {
        if (editorRef.current) editorRef.current.focus();
        else document.getElementById(inputId)?.focus();
      },
    }),
    [inputId],
  );

  const skeleton = <EditorSkeleton doc={doc} inputId={inputId} />;
  return (
    <div className={cn("min-w-0", locked && "cursor-progress")} aria-busy={locked || undefined}>
      <EditorLoadBoundary
        fallback={
          <div className="space-y-1">
            {skeleton}
            <p className="text-xs text-red-600" role="alert">
              The editor could not be loaded. Check your connection and reload the page.
            </p>
          </div>
        }
      >
        <Suspense fallback={skeleton}>
          <RichTextEditor
            ref={editorRef}
            content={doc}
            onChange={(next) => onChange(richValue(normalizeDoc(next)))}
            onBlur={onBlur}
            id={inputId}
            ariaLabelledBy={labelId}
            ariaDescribedBy={describedBy}
            ariaRequired={required}
            invalid={invalid}
            disabled={disabled || locked}
            placeholder={placeholder}
            toolbarLabel={label ? `Formatting for ${label}` : undefined}
          />
        </Suspense>
      </EditorLoadBoundary>
    </div>
  );
});
