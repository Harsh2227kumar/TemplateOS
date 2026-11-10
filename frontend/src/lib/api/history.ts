import { request, requestFile, type FileDownload } from "./client";
import { toQuery } from "./query-string";
import type {
  AuditActionOption,
  AuditLogItem,
  AuditLogParams,
  DownloadHistoryItem,
  DownloadHistoryParams,
  Paginated,
} from "./types";

/** V1.7 P3: download history and the admin audit log. */
export const historyApi = {
  myDownloads: async (params: DownloadHistoryParams = {}): Promise<Paginated<DownloadHistoryItem>> => {
    return request<Paginated<DownloadHistoryItem>>(`/me/downloads${toQuery(params)}`);
  },

  /** Owner only (403 otherwise). */
  documentDownloads: async (
    documentId: number,
    params: Pick<DownloadHistoryParams, "page" | "limit"> = {},
  ): Promise<Paginated<DownloadHistoryItem>> => {
    return request<Paginated<DownloadHistoryItem>>(`/documents/${documentId}/downloads${toQuery(params)}`);
  },

  /** 403 unless super / org / department admin; 422 for bad filters. */
  auditLogs: async (params: AuditLogParams = {}): Promise<Paginated<AuditLogItem>> => {
    return request<Paginated<AuditLogItem>>(`/admin/audit-logs${toQuery(params)}`);
  },

  auditActions: async (): Promise<AuditActionOption[]> => {
    return request<AuditActionOption[]>("/admin/audit-logs/actions");
  },

  /** The filtered rows as CSV (max 10,000), cookie auth. */
  exportAuditCsv: async (params: AuditLogParams = {}): Promise<FileDownload> => {
    const { page: _page, limit: _limit, ...filters } = params;
    return requestFile(`/admin/audit-logs/export.csv${toQuery(filters)}`);
  },
};
