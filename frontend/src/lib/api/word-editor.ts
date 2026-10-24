import { request } from "./client";
import type {
  EditorConfigResponse,
  EditorSessionRead,
  EditorStatusConfig,
  FieldChanges,
  TemplateResponse,
  TemplateRevision,
} from "./types";

/** V1.7 P2.1: the Word file editor (ONLYOFFICE Docs) and template file history. */
export const wordEditorApi = {
  /** Whether the editor is available and where its script lives (no auth needed). */
  editorConfig: async (): Promise<EditorStatusConfig> => {
    return request<EditorStatusConfig>("/system/editor-config");
  },

  /** A private copy of a template you can use, fields included. 201 = the copy. */
  customizeTemplate: async (templateId: number): Promise<TemplateResponse> => {
    return request<TemplateResponse>(`/templates/${templateId}/customize`, { method: "POST" });
  },

  /** Open the template's file. 403 not a manager, 409 being edited / no file, 503 disabled. */
  templateEditorSession: async (templateId: number): Promise<EditorConfigResponse> => {
    return request<EditorConfigResponse>(`/templates/${templateId}/editor-session`, { method: "POST" });
  },

  /** Open a generated version's DOCX (default: the latest). 409 / 410 / 404 / 503. */
  documentEditorSession: async (documentId: number, version?: number): Promise<EditorConfigResponse> => {
    const query = version ? `?version=${version}` : "";
    return request<EditorConfigResponse>(`/documents/${documentId}/editor-session${query}`, { method: "POST" });
  },

  /** Save status of your session (poll after closing the editor). */
  editorSession: async (sessionKey: string): Promise<EditorSessionRead> => {
    return request<EditorSessionRead>(`/editor/sessions/${encodeURIComponent(sessionKey)}`);
  },

  templateRevisions: async (templateId: number): Promise<TemplateRevision[]> => {
    return request<TemplateRevision[]>(`/templates/${templateId}/revisions`);
  },

  /** Make an older revision current (new revision). 403 / 404 / 410 / 422. */
  restoreTemplateRevision: async (templateId: number, revision: number): Promise<TemplateResponse> => {
    return request<TemplateResponse>(`/templates/${templateId}/revisions/${revision}/restore`, { method: "POST" });
  },

  fieldChanges: async (templateId: number): Promise<FieldChanges> => {
    return request<FieldChanges>(`/templates/${templateId}/field-changes`);
  },
};
