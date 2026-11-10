/**
 * V1.7 P2.1 Word editor hooks used only by lazily loaded modules (editor
 * pages, field changes, file history, template actions). Not re-exported from
 * the hooks barrel, so they stay out of the main bundle.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  wordEditorApi,
  type ApiError,
  type EditorConfigResponse,
  type EditorSessionRead,
  type FieldChanges,
  type TemplateResponse,
  type TemplateRevision,
} from "@/lib/api";
import { documentKeys, templateKeys, wordEditorKeys } from "@/lib/query/keys";

const isValidId = (id: number) => Number.isFinite(id) && id > 0;

/** "Customize for me": the new copy appears in my templates and the library. */
export function useCustomizeTemplate() {
  const queryClient = useQueryClient();
  return useMutation<TemplateResponse, ApiError, number>({
    mutationFn: (templateId) => wordEditorApi.customizeTemplate(templateId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

export type EditorTargetRef = { type: "template"; id: number } | { type: "document"; id: number; version?: number };

/** Open (or reuse) an editor session; called once by the editor page. */
export function useOpenEditorSession() {
  return useMutation<EditorConfigResponse, ApiError, EditorTargetRef>({
    mutationFn: (target) =>
      target.type === "template"
        ? wordEditorApi.templateEditorSession(target.id)
        : wordEditorApi.documentEditorSession(target.id, target.version),
  });
}

/** The save state, polled by the caller (see save-status.ts for the backoff). */
export function useEditorSession(sessionKey: string | null, refetchInterval: number | false) {
  return useQuery<EditorSessionRead, ApiError>({
    queryKey: wordEditorKeys.session(sessionKey ?? ""),
    queryFn: () => wordEditorApi.editorSession(sessionKey ?? ""),
    enabled: Boolean(sessionKey),
    refetchInterval,
    staleTime: 0,
  });
}

/** After a save: everything that shows the template's file or the document's versions. */
export function useInvalidateEditorTarget() {
  const queryClient = useQueryClient();
  return (session: Pick<EditorSessionRead, "template_id" | "document_id">) => {
    if (session.template_id) {
      void queryClient.invalidateQueries({ queryKey: templateKeys.detail(session.template_id) });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    }
    if (session.document_id) {
      void queryClient.invalidateQueries({ queryKey: documentKeys.detail(session.document_id) });
      void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    }
  };
}

export function useTemplateRevisions(templateId: number, options: { enabled?: boolean } = {}) {
  return useQuery<TemplateRevision[], ApiError>({
    queryKey: templateKeys.revisions(templateId),
    queryFn: () => wordEditorApi.templateRevisions(templateId),
    enabled: isValidId(templateId) && (options.enabled ?? true),
  });
}

export function useRestoreTemplateRevision() {
  const queryClient = useQueryClient();
  return useMutation<TemplateResponse, ApiError, { templateId: number; revision: number }>({
    mutationFn: ({ templateId, revision }) => wordEditorApi.restoreTemplateRevision(templateId, revision),
    onSettled: (_data, _error, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: templateKeys.detail(templateId) });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

export function useFieldChanges(templateId: number) {
  return useQuery<FieldChanges, ApiError>({
    queryKey: templateKeys.fieldChanges(templateId),
    queryFn: () => wordEditorApi.fieldChanges(templateId),
    enabled: isValidId(templateId),
    staleTime: 0,
    refetchOnMount: "always",
  });
}
