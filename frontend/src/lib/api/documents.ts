import { request, requestFile, type FileDownload } from "./client";
import type {
  Document,
  DocumentCreate,
  DocumentValuesResponse,
  DocumentValuesSave,
  GenerateDocumentResponse,
} from "./types";

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

  /** V1.6: render the DOCX (and PDF when the server can) from the SAVED values. */
  generate: async (documentId: number): Promise<GenerateDocumentResponse> => {
    return request<GenerateDocumentResponse>(`/documents/${documentId}/generate`, { method: "POST" });
  },

  /** V1.6: retry only the PDF conversion of the last generated DOCX. */
  retryPdf: async (documentId: number): Promise<GenerateDocumentResponse> => {
    return request<GenerateDocumentResponse>(`/documents/${documentId}/generate-pdf`, { method: "POST" });
  },

  /** V1.6: the generated file as a Blob (cookie auth). 404 not generated, 409 PDF unavailable. */
  download: async (documentId: number, format: "docx" | "pdf"): Promise<FileDownload> => {
    return requestFile(`/documents/${documentId}/download?format=${format}`);
  },
};
