import { request, requestFile, type FileDownload } from "./client";
import type {
  Document,
  DocumentCreate,
  DocumentPreview,
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

  /** V1.7: read-only preview (display values, completeness, generated files). 403/404 = not found. */
  getPreview: async (id: number): Promise<DocumentPreview> => {
    return request<DocumentPreview>(`/documents/${id}/preview`);
  },

  /**
   * V1.6: render the DOCX from the SAVED values, then convert it to PDF.
   * Always 200 once the DOCX exists; the PDF outcome is in pdf_status.
   */
  generate: async (documentId: number): Promise<GenerateDocumentResponse> => {
    return request<GenerateDocumentResponse>(`/documents/${documentId}/generate`, { method: "POST" });
  },

  /**
   * V1.6: retry only the PDF conversion of the last generated DOCX.
   * 503 = conversion failed (detail is the reason, already recorded),
   * 410 = the generated DOCX is missing, 404 = not generated.
   */
  retryPdf: async (documentId: number): Promise<GenerateDocumentResponse> => {
    return request<GenerateDocumentResponse>(`/documents/${documentId}/generate-pdf`, { method: "POST" });
  },

  /**
   * V1.6: the generated file as a Blob (cookie auth). 404 not generated;
   * PDF: 409 no PDF, 410 the PDF file is missing on the server.
   */
  download: async (documentId: number, format: "docx" | "pdf"): Promise<FileDownload> => {
    return requestFile(
      format === "pdf" ? `/documents/${documentId}/download/pdf` : `/documents/${documentId}/download?format=docx`,
    );
  },
};
