import { request } from "./client";
import type { Document, DocumentCreate, DocumentValuesResponse, DocumentValuesSave } from "./types";

export const documentsApi = {
  createDocument: async (body: DocumentCreate): Promise<Document> => {
    return request<Document>("/documents/create", { method: "POST", body: JSON.stringify(body) });
  },

  saveValues: async (documentId: number, body: DocumentValuesSave): Promise<DocumentValuesResponse> => {
    return request<DocumentValuesResponse>(`/documents/${documentId}/values`, { method: "PUT", body: JSON.stringify(body) });
  },

  getMyDocuments: async (): Promise<Document[]> => {
    return request<Document[]>("/documents");
  },

  getDocument: async (id: number): Promise<Document> => {
    return request<Document>(`/documents/${id}`);
  },
};
