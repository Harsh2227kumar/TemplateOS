import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  templateAccessApi,
  templatesApi,
  type ApiError,
  type TemplateAccessUpdate,
  type TemplateLibraryParams,
  type TemplateResponse,
  type TemplateUploadPayload,
} from "@/lib/api";
import { templateKeys } from "@/lib/query/keys";

const isValidId = (id: number) => Number.isFinite(id) && id > 0;

// ── queries ────────────────────────────────────────────────────────────────

/** Templates uploaded by the current user (dashboard). */
export function useMyTemplates() {
  return useQuery({
    queryKey: templateKeys.mine(),
    queryFn: () => templatesApi.getMyTemplates(),
  });
}

/** One page of the template library with its filters. */
export function useTemplateLibrary(params: TemplateLibraryParams) {
  return useQuery({
    queryKey: templateKeys.library(params),
    queryFn: () => templatesApi.getLibrary(params),
  });
}

export function useTemplate(id: number, options: { enabled?: boolean } = {}) {
  return useQuery<TemplateResponse, ApiError>({
    queryKey: templateKeys.detail(id),
    queryFn: () => templatesApi.getTemplateDetail(id),
    enabled: isValidId(id) && (options.enabled ?? true),
  });
}

/** Audience choices for upload / manage access. Rarely changes, so cached longer. */
export function useTemplateAccessOptions(enabled = true) {
  return useQuery({
    queryKey: templateKeys.accessOptions(),
    queryFn: () => templateAccessApi.getOptions(),
    enabled,
    staleTime: 5 * 60_000,
  });
}

// ── mutations ──────────────────────────────────────────────────────────────

export function useUploadTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TemplateUploadPayload) => templatesApi.upload(payload),
    onSuccess: (template) => {
      queryClient.setQueryData(templateKeys.detail(template.id), template);
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => templatesApi.deleteTemplate(id),
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: templateKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

export function useUpdateTemplateAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: TemplateAccessUpdate }) =>
      templateAccessApi.update(id, body),
    onSuccess: (template) => {
      queryClient.setQueryData(templateKeys.detail(template.id), template);
      // Visibility decides who sees it in the library.
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}
