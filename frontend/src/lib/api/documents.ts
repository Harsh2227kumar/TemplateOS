import { request } from "./client";
import type { Document, DocumentCreate, DocumentValuesResponse, DocumentValuesSave } from "./types";

export const documentsApi = {
  createDocument: async (token: string, body: DocumentCreate): Promise<Document> => {
    return request<Document>("/documents/create", { method: "POST", body: JSON.stringify(body) }, token);
  },

  saveValues: async (token: string, documentId: number, body: DocumentValuesSave): Promise<DocumentValuesResponse> => {
    return request<DocumentValuesResponse>(`/documents/${documentId}/values`, { method: "PUT", body: JSON.stringify(body) }, token);
  },

  getMyDocuments: async (token: string): Promise<Document[]> => {
    return request<Document[]>("/documents", {}, token);
  },

  getDocument: async (token: string, id: number): Promise<Document> => {
    return request<Document>(`/documents/${id}`, {}, token);
  },
};
