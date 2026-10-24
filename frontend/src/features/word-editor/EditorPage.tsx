import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ChevronLeft, FileText, Loader2, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useInvalidateEditorTarget, useOpenEditorSession, type EditorTargetRef } from "@/hooks/queries/word-editor-actions";
import { ApiError, wordEditorApi, type EditorConfigResponse, type EditorSessionRead } from "@/lib/api";

import { OnlyOfficeEditor } from "./OnlyOfficeEditor";
import {
  isFinal,
  nextPollDelay,
  openErrorMessage,
  SAVE_POLL_TIMEOUT_MS,
  sessionMessage,
  STILL_SAVING_MESSAGE,
} from "./save-status";

interface EditorPageProps {
  target: EditorTargetRef;
  /** Header file name until the editor config is known. */
  fileName: string;
  backTo: string;
  backLabel: string;
  /** Side panel next to the editor (template help). */
  help?: ReactNode;
  /** A final "saved" state: navigate on (the target's queries are already invalidated). */
  onSaved: (session: EditorSessionRead) => void;
}

type Phase =
  | { kind: "opening" }
  | { kind: "open-error"; status?: number; message: string }
  | { kind: "editing"; editor: EditorConfigResponse; ready: boolean; error: string | null }
  | { kind: "saving"; editor: EditorConfigResponse; session: EditorSessionRead | null; timedOut: boolean }
  | { kind: "done"; editor: EditorConfigResponse; session: EditorSessionRead };

/**
 * V1.7 P2.1 shared editor layout: opens (or reuses) the session, shows the
 * ONLYOFFICE editor, and after "Done editing" polls the save state until a
 * final status (1 s → 2 s, gives up waiting after 90 s).
 */
export function EditorPage({ target, fileName, backTo, backLabel, help, onSaved }: EditorPageProps) {
  const openSession = useOpenEditorSession();
  const invalidate = useInvalidateEditorTarget();
  const [phase, setPhase] = useState<Phase>({ kind: "opening" });
  const [attempt, setAttempt] = useState(0);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  const targetKey = JSON.stringify(target);

  const open = () => {
    setPhase({ kind: "opening" });
    openSession.mutate(target, {
      onSuccess: (editor) => setPhase({ kind: "editing", editor, ready: false, error: null }),
      onError: (error) =>
        setPhase({
          kind: "open-error",
          status: error instanceof ApiError ? error.status : undefined,
          message: openErrorMessage(error instanceof ApiError ? error.status : undefined, error.message),
        }),
    });
  };

  // Open once per target (StrictMode-safe: the backend reuses my own session).
  useEffect(() => {
    open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetKey]);

  // Poll the save after "Done editing".
  const savingKey = phase.kind === "saving" && !phase.timedOut ? phase.editor.session_key : null;
  const startedRef = useRef(0);
  useEffect(() => {
    if (!savingKey) return;
    if (attempt === 0) startedRef.current = Date.now();
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const session = await wordEditorApi.editorSession(savingKey);
        if (cancelled) return;
        if (isFinal(session.status)) {
          if (session.status === "saved") invalidate(session);
          setPhase((current) => (current.kind === "saving" ? { kind: "done", editor: current.editor, session } : current));
          if (session.status === "saved") onSavedRef.current(session);
          return;
        }
        const timedOut = Date.now() - startedRef.current > SAVE_POLL_TIMEOUT_MS;
        setPhase((current) => (current.kind === "saving" ? { ...current, session, timedOut } : current));
      } catch {
        if (cancelled) return;
      }
      setAttempt((n) => n + 1);
    }, nextPollDelay(attempt));
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savingKey, attempt]);

  const handleDone = () => {
    if (phase.kind !== "editing") return;
    setAttempt(0);
    // Unmounting OnlyOfficeEditor destroys it: the Document Server then saves.
    setPhase({ kind: "saving", editor: phase.editor, session: null, timedOut: false });
  };

  const title =
    phase.kind === "editing" || phase.kind === "saving" || phase.kind === "done"
      ? String((phase.editor.config.document as { title?: string } | undefined)?.title ?? fileName)
      : fileName;
  const targetType = target.type;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <Button variant="ghost" size="sm" asChild className="-ml-2 h-8 px-2 text-slate-600">
            <Link to={backTo}>
              <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
              {backLabel}
            </Link>
          </Button>
          <h1 className="flex min-w-0 items-center gap-2 text-lg font-semibold text-slate-900">
            <FileText className="h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" />
            <span className="truncate" title={title}>
              {title}
            </span>
          </h1>
        </div>
        {phase.kind === "editing" && (
          <Button type="button" onClick={handleDone} className="w-full shrink-0 sm:w-auto">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Done editing
          </Button>
        )}
      </div>

      <div role="status" aria-live="polite" className="text-sm">
        {phase.kind === "opening" && (
          <p className="flex items-center gap-2 text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Opening the document editor…
          </p>
        )}
        {phase.kind === "editing" && !phase.ready && !phase.error && (
          <p className="flex items-center gap-2 text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Loading the file…
          </p>
        )}
        {phase.kind === "editing" && phase.ready && (
          <p className="text-slate-500">
            Changes are kept while you edit. Click <span className="font-medium">Done editing</span> to save them
            {targetType === "document" ? " as a new version." : " to the template."}
          </p>
        )}
        {phase.kind === "saving" && (
          <p className="flex items-center gap-2 text-slate-700">
            {!phase.timedOut && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {phase.timedOut
              ? STILL_SAVING_MESSAGE
              : phase.session
                ? sessionMessage(phase.session, targetType)
                : "Saving your changes…"}
          </p>
        )}
      </div>

      {phase.kind === "open-error" && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4" role="alert">
          <p className="flex items-start gap-2 text-sm text-amber-900">
            {phase.status === 409 ? (
              <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            {phase.message}
          </p>
          <div className="flex gap-2">
            <Button asChild variant="outline" size="sm" className="bg-white">
              <Link to={backTo}>Back</Link>
            </Button>
            {phase.status !== 503 && phase.status !== 403 && phase.status !== 410 && (
              <Button type="button" size="sm" onClick={open}>
                Try again
              </Button>
            )}
          </div>
        </div>
      )}

      {phase.kind === "editing" && phase.error && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
          <p className="text-sm text-red-800">{phase.error}</p>
          <Button type="button" size="sm" variant="outline" className="bg-white" onClick={open}>
            Open the editor again
          </Button>
        </div>
      )}

      {phase.kind === "done" && phase.session.status !== "saved" && (
        <div
          className={`flex flex-col items-start gap-3 rounded-lg border p-4 ${
            phase.session.status === "closed" ? "border-slate-200 bg-slate-50" : "border-red-200 bg-red-50"
          }`}
          role={phase.session.status === "closed" ? "status" : "alert"}
        >
          <p className={`text-sm ${phase.session.status === "closed" ? "text-slate-700" : "text-red-800"}`}>
            {sessionMessage(phase.session, targetType)}
          </p>
          <div className="flex gap-2">
            <Button asChild variant="outline" size="sm" className="bg-white">
              <Link to={backTo}>{backLabel}</Link>
            </Button>
            <Button type="button" size="sm" onClick={open}>
              Open the editor again
            </Button>
          </div>
        </div>
      )}

      {phase.kind === "editing" && !phase.error && (
        <div className={help ? "grid gap-3 lg:grid-cols-[minmax(0,1fr)_16rem]" : undefined}>
          <OnlyOfficeEditor
            documentServerUrl={phase.editor.document_server_url}
            config={phase.editor.config}
            title={`Document editor: ${title}`}
            onReady={() => setPhase((current) => (current.kind === "editing" ? { ...current, ready: true } : current))}
            onError={(message) =>
              setPhase((current) => (current.kind === "editing" ? { ...current, error: message } : current))
            }
          />
          {help && <aside className="order-first lg:order-none">{help}</aside>}
        </div>
      )}
    </div>
  );
}
