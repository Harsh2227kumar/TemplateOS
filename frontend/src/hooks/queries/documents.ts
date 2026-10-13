import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  documentsApi,
  type ApiError,
  type Document,
  type DocumentCreate,
  type DocumentValuesSave,
} from "@/lib/api";
import { serverTime } from "@/lib/dates";
import { documentKeys } from "@/lib/query/keys";

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
