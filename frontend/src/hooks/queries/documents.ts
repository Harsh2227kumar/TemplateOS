import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  documentsApi,
  type ApiError,
  type Document,
  type DocumentCreate,
  type DocumentPreview,
  type DocumentValuesSave,
  type DocumentVersion,
  type DocumentVersionDetail,
  type GenerateDocumentResponse,
} from "@/lib/api";
import { serverTime } from "@/lib/dates";
import { saveBlob } from "@/lib/download";
import { documentKeys } from "@/lib/query/keys";
import {
  fallbackDownloadFilename,
  filenameFromContentDisposition,
  type DownloadFormat,
} from "@/features/documents/generation";

const isValidId = (id: number) => Number.isFinite(id) && id > 0;

/** Most recently edited first; drafts with an unreadable date go last. */
function sortByUpdated(documents: Document[]): Document[] {
  return [...documents].sort((a, b) => serverTime(b.updated_at) - serverTime(a.updated_at));
}

export function useMyDocuments() {
  return useQuery<Document[], ApiError>({
    queryKey: documentKeys.mine(),
    queryFn: () => documentsApi.getMyDocuments(),
    select: sortByUpdated,
  });
}

export function useDocument(id: number) {
  return useQuery<Document, ApiError>({
    queryKey: documentKeys.detail(id),
    queryFn: () => documentsApi.getDocument(id),
    enabled: isValidId(id),
  });
}

/**
 * V1.7 read-only preview. Always refetched on mount (staleTime 0) so it is
 * fresh after edits or generation. Its key sits under documentKeys.detail(id),
 * so the save / generate / retry-PDF invalidations below refresh it too.
 */
export function useDocumentPreview(id: number) {
  return useQuery<DocumentPreview, ApiError>({
    queryKey: documentKeys.preview(id),
    queryFn: () => documentsApi.getPreview(id),
    enabled: isValidId(id),
    staleTime: 0,
    refetchOnMount: "always",
  });
}

export function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DocumentCreate) => documentsApi.createDocument(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}

export function useSaveDocumentValues() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, body }: { documentId: number; body: DocumentValuesSave }) =>
      documentsApi.saveValues(documentId, body),
    onSuccess: () => {
      // The dashboard list ("edited x ago"), the draft and its preview changed.
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}

/**
 * Generating changes the draft (status, generated info), its preview
 * (documentKeys.preview(id) is under detail(id)) and the dashboard list.
 */
function useInvalidateDocument() {
  const queryClient = useQueryClient();
  return (documentId: number) => {
    void queryClient.invalidateQueries({ queryKey: documentKeys.detail(documentId) });
    void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
  };
}

export interface GenerateRequest {
  documentId: number;
  /** V1.7 P2.1: confirmed replacing a manually edited latest version. */
  replaceManualEdits?: boolean;
}

/**
 * POST /documents/{id}/generate. A 422 carries field errors like a save;
 * a 409 with code "manual_edits" asks first (see manualEditsConflict).
 */
export function useGenerateDocument() {
  const invalidate = useInvalidateDocument();
  return useMutation<GenerateDocumentResponse, ApiError, GenerateRequest>({
    mutationFn: ({ documentId, replaceManualEdits }) => documentsApi.generate(documentId, { replaceManualEdits }),
    onSettled: (_data, _error, { documentId }) => invalidate(documentId),
  });
}

/** POST /documents/{id}/generate-pdf (retry the PDF only). */
export function useRetryPdf() {
  const invalidate = useInvalidateDocument();
  return useMutation<GenerateDocumentResponse, ApiError, number>({
    mutationFn: (documentId) => documentsApi.retryPdf(documentId),
    onSettled: (_data, _error, documentId) => invalidate(documentId),
  });
}

export interface DownloadRequest {
  documentId: number;
  format: DownloadFormat;
  /** Draft name, for the fallback filename when the header is not readable. */
  name?: string | null;
}

/** Fetch a generated file with the session cookies and save it. */
export function useDownloadGenerated() {
  return useMutation<string, ApiError, DownloadRequest>({
    mutationFn: async ({ documentId, format, name }) => {
      const file = await documentsApi.download(documentId, format);
      const filename =
        filenameFromContentDisposition(file.contentDisposition) ??
        fallbackDownloadFilename(name, documentId, format);
      saveBlob(file.blob, filename);
      return filename;
    },
  });
}

// ── V1.7 Phase 2: document versions ──────────────────────────────

/** Every generated version, newest first (refreshed by generate / restore). */
export function useDocumentVersions(id: number, options: { enabled?: boolean } = {}) {
  return useQuery<DocumentVersion[], ApiError>({
    queryKey: documentKeys.versions(id),
    queryFn: () => documentsApi.listVersions(id),
    enabled: isValidId(id) && (options.enabled ?? true),
  });
}

/** One version with its values. */
export function useDocumentVersion(id: number, version: number) {
  return useQuery<DocumentVersionDetail, ApiError>({
    queryKey: documentKeys.version(id, version),
    queryFn: () => documentsApi.getVersion(id, version),
    enabled: isValidId(id) && Number.isInteger(version) && version > 0,
  });
}

/** POST /versions/{n}/restore: the draft's values become the version's. */
export function useRestoreVersion() {
  const queryClient = useQueryClient();
  return useMutation<Document, ApiError, { documentId: number; version: number }>({
    mutationFn: ({ documentId, version }) => documentsApi.restoreVersion(documentId, version),
    onSuccess: (document, { documentId }) => {
      queryClient.setQueryData(documentKeys.detail(documentId), document);
    },
    onSettled: (_data, _error, { documentId }) => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.detail(documentId) });
      void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

export interface VersionDownloadRequest extends DownloadRequest {
  version: number;
}

/** Fetch one version's file with the session cookies and save it. */
export function useDownloadVersion() {
  return useMutation<string, ApiError, VersionDownloadRequest>({
    mutationFn: async ({ documentId, version, format, name }) => {
      const file = await documentsApi.downloadVersion(documentId, version, format);
      const plainName = fallbackDownloadFilename(name, documentId, format);
      const fallback = `${plainName.slice(0, -(format.length + 1))} v${version}.${format}`;
      const filename = filenameFromContentDisposition(file.contentDisposition) ?? fallback;
      saveBlob(file.blob, filename);
      return filename;
    },
  });
}
