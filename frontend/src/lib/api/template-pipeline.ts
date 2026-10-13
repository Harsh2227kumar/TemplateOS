import { request } from "./client";
import type {
  CleanPreviewResponse,
  CleanResponse,
  CleanSuggestionsResponse,
  CleanTemplatePayload,
  FieldSyncPayload,
  PlaceholderDetectionResponse,
  PlaceholderFix,
  SuggestFieldsResponse,
  TemplateContent,
  TemplateField,
  TemplateFieldUpsert,
} from "./types";

/**
 * Template preparation pipeline: cleaning, placeholder detection and the
 * field metadata editor.
 */
export const templatePipelineApi = {
  detectPlaceholders: async (token: string, id: number, force = false): Promise<PlaceholderDetectionResponse> => {
    return request<PlaceholderDetectionResponse>(
      `/templates/${id}/detect-placeholders${force ? "?force=true" : ""}`,
      { method: "POST" },
      token,
    );
  },

  getFields: async (token: string, id: number): Promise<TemplateField[]> => {
    return request<TemplateField[]>(`/templates/${id}/fields`, {}, token);
  },

  createField: async (
    token: string,
    id: number,
    body: TemplateFieldUpsert,
  ): Promise<TemplateField> => {
    return request<TemplateField>(
      `/templates/${id}/fields`,
      { method: "POST", body: JSON.stringify(body) },
      token,
    );
  },

  updateField: async (
    token: string,
    id: number,
    fieldId: number,
    body: Partial<TemplateFieldUpsert>,
  ): Promise<TemplateField> => {
    return request<TemplateField>(
      `/templates/${id}/fields/${fieldId}`,
      { method: "PATCH", body: JSON.stringify(body) },
      token,
    );
  },

  deleteField: async (token: string, id: number, fieldId: number): Promise<void> => {
    return request<void>(
      `/templates/${id}/fields/${fieldId}`,
      { method: "DELETE" },
      token,
    );
  },

  reorderFields: async (
    token: string,
    id: number,
    orderedIds: number[],
  ): Promise<TemplateField[]> => {
    return request<TemplateField[]>(
      `/templates/${id}/fields/reorder`,
      { method: "PUT", body: JSON.stringify({ ordered_ids: orderedIds }) },
      token,
    );
  },

  saveFields: async (
    token: string,
    id: number,
    payload: FieldSyncPayload,
  ): Promise<TemplateField[]> => {
    return request<TemplateField[]>(
      `/templates/${id}/fields`,
      { method: "PUT", body: JSON.stringify(payload) },
      token,
    );
  },

  suggestFields: async (
    token: string,
    id: number,
  ): Promise<SuggestFieldsResponse> => {
    return request<SuggestFieldsResponse>(
      `/templates/${id}/suggest-fields`,
      { method: "POST" },
      token,
    );
  },

  getContent: async (
    token: string,
    id: number,
    source: "original" | "processed" = "original",
  ): Promise<TemplateContent> => {
    const query = source === "processed" ? "?source=processed" : "";
    return request<TemplateContent>(`/templates/${id}/content${query}`, {}, token);
  },

  getCleanSuggestions: async (token: string, id: number): Promise<CleanSuggestionsResponse> => {
    return request<CleanSuggestionsResponse>(`/templates/${id}/clean-suggestions`, {}, token);
  },

  previewClean: async (
    token: string,
    id: number,
    payload: CleanTemplatePayload,
  ): Promise<CleanPreviewResponse> => {
    return request<CleanPreviewResponse>(
      `/templates/${id}/clean-preview`,
      { method: "POST", body: JSON.stringify(payload) },
      token,
    );
  },

  fixPlaceholders: async (
    token: string,
    id: number,
    fixes: PlaceholderFix[],
  ): Promise<PlaceholderDetectionResponse> => {
    return request<PlaceholderDetectionResponse>(
      `/templates/${id}/fix-placeholders`,
      { method: "POST", body: JSON.stringify({ fixes }) },
      token,
    );
  },

  cleanTemplate: async (
    token: string,
    id: number,
    payload: CleanTemplatePayload,
  ): Promise<CleanResponse> => {
    return request<CleanResponse>(
      `/templates/${id}/clean`,
      { method: "POST", body: JSON.stringify(payload) },
      token,
    );
  },
};
