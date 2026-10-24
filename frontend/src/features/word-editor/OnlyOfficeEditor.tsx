import { useEffect, useId, useLayoutEffect, useRef } from "react";

import { loadDocsApi, type DocEditorInstance } from "./load-docs-api";

interface OnlyOfficeEditorProps {
  documentServerUrl: string;
  /** The signed config from the backend: passed on unchanged (events are added beside it). */
  config: Record<string, unknown>;
  title: string;
  onReady?: () => void;
  onError?: (message: string) => void;
}

/**
 * The ONLYOFFICE editor in a full-height container. Mounts once per config;
 * unmounting destroys the editor, which tells the Document Server the user
 * left (it then saves and calls the backend back).
 */
export function OnlyOfficeEditor({ documentServerUrl, config, title, onReady, onError }: OnlyOfficeEditorProps) {
  const elementId = `onlyoffice-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const callbacks = useRef({ onReady, onError });
  callbacks.current = { onReady, onError };
  const editorRef = useRef<DocEditorInstance | null>(null);

  // Destroy while the editor's iframe is still in the page (a layout cleanup
  // runs before React removes the DOM; a passive one runs after).
  useLayoutEffect(
    () => () => {
      const editor = editorRef.current;
      editorRef.current = null;
      try {
        editor?.destroyEditor();
      } catch {
        // Already gone (e.g. the script failed half-way).
      }
    },
    [documentServerUrl, config, elementId, title],
  );

  useEffect(() => {
    let cancelled = false;
    loadDocsApi(documentServerUrl)
      .then((api) => {
        if (cancelled) return;
        editorRef.current = new api.DocEditor(elementId, {
          ...config,
          width: "100%",
          height: "100%",
          events: {
            onDocumentReady: () => callbacks.current.onReady?.(),
            onError: (event: { data?: { errorDescription?: string } }) =>
              callbacks.current.onError?.(event?.data?.errorDescription || "The document editor reported an error"),
          },
        });
        // The editor replaces the placeholder div with an iframe: give it a title.
        const frame = document.querySelector<HTMLIFrameElement>(`iframe[name="frameEditor"]`);
        if (frame) frame.title = title;
      })
      .catch((error: unknown) => {
        if (!cancelled) callbacks.current.onError?.(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, [documentServerUrl, config, elementId, title]);

  return (
    <div className="h-[calc(100vh-11rem)] min-h-[28rem] w-full overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div id={elementId} />
    </div>
  );
}
