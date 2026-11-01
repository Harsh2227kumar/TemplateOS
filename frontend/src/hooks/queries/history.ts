import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import {
  historyApi,
  type ApiError,
  type AuditActionOption,
  type AuditLogItem,
  type AuditLogParams,
  type DownloadHistoryItem,
  type DownloadHistoryParams,
  type Paginated,
} from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { auditKeys, historyKeys } from "@/lib/query/keys";
import { filenameFromContentDisposition } from "@/features/documents/generation";

/** V1.7 P3: your own downloads (refreshed after every download). */
export function useMyDownloads(params: DownloadHistoryParams) {
  return useQuery<Paginated<DownloadHistoryItem>, ApiError>({
    queryKey: historyKeys.myDownloads(params),
    queryFn: () => historyApi.myDownloads(params),
    placeholderData: keepPreviousData,
  });
}

export function useDocumentDownloads(documentId: number, params: { page?: number; limit?: number }, enabled = true) {
  return useQuery<Paginated<DownloadHistoryItem>, ApiError>({
    queryKey: historyKeys.documentDownloads(documentId, params),
    queryFn: () => historyApi.documentDownloads(documentId, params),
    enabled: enabled && Number.isFinite(documentId) && documentId > 0,
    placeholderData: keepPreviousData,
  });
}

export function useAuditLogs(params: AuditLogParams, enabled = true) {
  return useQuery<Paginated<AuditLogItem>, ApiError>({
    queryKey: auditKeys.list(params),
    queryFn: () => historyApi.auditLogs(params),
    enabled,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useAuditActions() {
  return useQuery<AuditActionOption[], ApiError>({
    queryKey: auditKeys.actions(),
    queryFn: () => historyApi.auditActions(),
    staleTime: 60 * 60_000,
    retry: false,
  });
}

/** Save the filtered audit log as CSV; resolves to the file name. */
export function useExportAuditCsv() {
  return useMutation<string, ApiError, AuditLogParams>({
    mutationFn: async (params) => {
      const file = await historyApi.exportAuditCsv(params);
      const filename = filenameFromContentDisposition(file.contentDisposition) ?? "audit-log.csv";
      saveBlob(file.blob, filename);
      return filename;
    },
  });
}
