import { useQuery } from "@tanstack/react-query";

import { wordEditorApi, type ApiError, type EditorStatusConfig } from "@/lib/api";
import { wordEditorKeys } from "@/lib/query/keys";

// The editor's mutations and session / revision queries are in
// word-editor-actions.ts, imported only by the lazy editor pages.

/** V1.7 P2.1: is the Word editor available? Entry points stay hidden until this says so. */
export function useEditorConfig() {
  return useQuery<EditorStatusConfig, ApiError>({
    queryKey: wordEditorKeys.config(),
    queryFn: () => wordEditorApi.editorConfig(),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** True only once the server said the editor is enabled. */
export function useEditorEnabled(): boolean {
  return useEditorConfig().data?.enabled === true;
}
