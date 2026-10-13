import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  templatesApi,
  type ApiError,
  type CleanTemplatePayload,
  type FieldSyncPayload,
  type PlaceholderDetectionResponse,
  type PlaceholderFix,
  type TemplateField,
  type TemplateResponse,
} from "@/lib/api";
import { templateKeys } from "@/lib/query/keys";

const isValidId = (id: number) => Number.isFinite(id) && id > 0;

/** Server status changes (uploaded -> placeholder_detected -> field_configured) show in lists too. */
function setTemplateStatus(queryClient: QueryClient, id: number, status: string | undefined) {
  if (!status) return;
  queryClient.setQueryData<TemplateResponse>(templateKeys.detail(id), (prev) =>
    prev ? { ...prev, status } : prev,
  );
}

// ── queries ────────────────────────────────────────────────────────────────

export function useTemplateFields(id: number, options: { enabled?: boolean } = {}) {
  return useQuery<TemplateField[], ApiError>({
    queryKey: templateKeys.fields(id),
    queryFn: () => templatesApi.getFields(id),
    enabled: isValidId(id) && (options.enabled ?? true),
  });
}

export function useTemplateContent(id: number, source: "original" | "processed" = "original") {
  return useQuery({
    queryKey: templateKeys.content(id, source),
    queryFn: () => templatesApi.getContent(id, source),
    enabled: isValidId(id),
  });
}

/** Automatic cleaning suggestions; only template managers may ask. */
export function useCleanSuggestions(id: number, enabled: boolean) {
  return useQuery({
    queryKey: templateKeys.cleanSuggestions(id),
    queryFn: () => templatesApi.getCleanSuggestions(id),
    enabled: isValidId(id) && enabled,
  });
}

// ── mutations ──────────────────────────────────────────────────────────────

/** Detection and placeholder fixes both return the full field list. */
function useApplyDetection(id: number) {
  const queryClient = useQueryClient();
  return (result: PlaceholderDetectionResponse) => {
    queryClient.setQueryData(templateKeys.fields(id), result.detected_fields);
    setTemplateStatus(queryClient, id, result.status);
    void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
  };
}

export function useDetectPlaceholders(id: number) {
  const applyDetection = useApplyDetection(id);
  return useMutation({
    mutationFn: (force: boolean) => templatesApi.detectPlaceholders(id, force),
    onSuccess: applyDetection,
  });
}

export function useFixPlaceholders(id: number) {
  const applyDetection = useApplyDetection(id);
  return useMutation({
    mutationFn: (fixes: PlaceholderFix[]) => templatesApi.fixPlaceholders(id, fixes),
    onSuccess: applyDetection,
  });
}

/** Dry run: nothing is saved, so nothing is invalidated. */
export function usePreviewClean(id: number) {
  return useMutation({
    mutationFn: (payload: CleanTemplatePayload) => templatesApi.previewClean(id, payload),
  });
}

export function useCleanTemplate(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CleanTemplatePayload) => templatesApi.cleanTemplate(id, payload),
    onSuccess: () => {
      // New processed copy: the template (status, processed path), its fields,
      // content and suggestions are all out of date.
      void queryClient.invalidateQueries({ queryKey: templateKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

/** Field Setup "Save all": replaces the field set. */
export function useSaveTemplateFields(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FieldSyncPayload) => templatesApi.saveFields(id, payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(templateKeys.fields(id), saved);
      // mark_configured may have changed the status.
      void queryClient.invalidateQueries({ queryKey: templateKeys.detail(id), exact: true });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

/** AI field proposals. Nothing persists until the user saves, so no cache. */
export function useSuggestFields(id: number) {
  return useMutation({
    mutationFn: () => templatesApi.suggestFields(id),
  });
}
