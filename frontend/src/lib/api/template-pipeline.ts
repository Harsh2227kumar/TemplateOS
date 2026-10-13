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
  detectPlaceholders: async (id: number, force = false): Promise<PlaceholderDetectionResponse> => {
    return request<PlaceholderDetectionResponse>(
      `/templates/${id}/detect-placeholders${force ? "?force=true" : ""}`,
      { method: "POST" },
    );
  },

  getFields: async (id: number): Promise<TemplateField[]> => {
    return request<TemplateField[]>(`/templates/${id}/fields`);
  },

  createField: async (
    id: number,
    body: TemplateFieldUpsert,
  ): Promise<TemplateField> => {
    return request<TemplateField>(
      `/templates/${id}/fields`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  updateField: async (
    id: number,
    fieldId: number,
    body: Partial<TemplateFieldUpsert>,
  ): Promise<TemplateField> => {
    return request<TemplateField>(
      `/templates/${id}/fields/${fieldId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },

  deleteField: async (id: number, fieldId: number): Promise<void> => {
    return request<void>(
      `/templates/${id}/fields/${fieldId}`,
      { method: "DELETE" },
    );
  },

  reorderFields: async (
    id: number,
    orderedIds: number[],
  ): Promise<TemplateField[]> => {
    return request<TemplateField[]>(
      `/templates/${id}/fields/reorder`,
      { method: "PUT", body: JSON.stringify({ ordered_ids: orderedIds }) },
    );
  },

  saveFields: async (
    id: number,
    payload: FieldSyncPayload,
  ): Promise<TemplateField[]> => {
    return request<TemplateField[]>(
      `/templates/${id}/fields`,
      { method: "PUT", body: JSON.stringify(payload) },
    );
  },

  suggestFields: async (
    id: number,
  ): Promise<SuggestFieldsResponse> => {
    return request<SuggestFieldsResponse>(
      `/templates/${id}/suggest-fields`,
      { method: "POST" },
    );
  },

  getContent: async (
    id: number,
    source: "original" | "processed" = "original",
  ): Promise<TemplateContent> => {
    const query = source === "processed" ? "?source=processed" : "";
    return request<TemplateContent>(`/templates/${id}/content${query}`);
  },

  getCleanSuggestions: async (id: number): Promise<CleanSuggestionsResponse> => {
    return request<CleanSuggestionsResponse>(`/templates/${id}/clean-suggestions`);
  },

  previewClean: async (
    id: number,
    payload: CleanTemplatePayload,
  ): Promise<CleanPreviewResponse> => {
    return request<CleanPreviewResponse>(
      `/templates/${id}/clean-preview`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  fixPlaceholders: async (
    id: number,
    fixes: PlaceholderFix[],
  ): Promise<PlaceholderDetectionResponse> => {
    return request<PlaceholderDetectionResponse>(
      `/templates/${id}/fix-placeholders`,
      { method: "POST", body: JSON.stringify({ fixes }) },
    );
  },

  cleanTemplate: async (
    id: number,
    payload: CleanTemplatePayload,
  ): Promise<CleanResponse> => {
    return request<CleanResponse>(
      `/templates/${id}/clean`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },
};
