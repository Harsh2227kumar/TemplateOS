import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  documentsApi,
  type ApiError,
  type Document,
  type DocumentCreate,
  type DocumentValuesSave,
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
      // The dashboard list ("edited x ago") and the draft itself changed.
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}

/** Generating changes the draft (status, generated info) and the dashboard list. */
function useInvalidateDocument() {
  const queryClient = useQueryClient();
  return (documentId: number) => {
    void queryClient.invalidateQueries({ queryKey: documentKeys.detail(documentId) });
    void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
  };
}

/** POST /documents/{id}/generate. A 422 carries field errors like a save. */
export function useGenerateDocument() {
  const invalidate = useInvalidateDocument();
  return useMutation<GenerateDocumentResponse, ApiError, number>({
    mutationFn: (documentId) => documentsApi.generate(documentId),
    onSettled: (_data, _error, documentId) => invalidate(documentId),
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
