import { request, uploadForm } from "./client";
import { templatePipelineApi } from "./template-pipeline";
import type {
  TemplateAccessOptions,
  TemplateAccessUpdate,
  TemplateLibraryResponse,
  TemplateListItem,
  TemplateResponse,
} from "./types";

export interface TemplateLibraryParams {
  search?: string;
  category?: string;
  visibility?: string;
  status?: string;
  page?: number;
  limit?: number;
}

export interface TemplateUploadPayload {
  file: File;
  name: string;
  description?: string;
  category: string;
  visibility: string;
  scope_organization?: string;
  scope_department?: string;
  allowed_roles?: string[];
}

/** Library, detail, ownership and upload of templates. */
export const templateCatalogApi = {
  getLibrary: async (token: string, params?: TemplateLibraryParams): Promise<TemplateLibraryResponse> => {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== "") {
          searchParams.append(key, String(value));
        }
      });
    }
    const queryString = searchParams.toString();
    const url = `/templates/library${queryString ? `?${queryString}` : ""}`;
    return request<TemplateLibraryResponse>(url, {}, token);
  },

  getTemplateDetail: async (token: string, id: number): Promise<TemplateResponse> => {
    return request<TemplateResponse>(`/templates/${id}`, {}, token);
  },

  getMyTemplates: async (token: string): Promise<TemplateListItem[]> => {
    return request<TemplateListItem[]>("/templates/", {}, token);
  },

  deleteTemplate: async (token: string, id: number): Promise<void> => {
    return request<void>(`/templates/${id}`, { method: "DELETE" }, token);
  },

  upload: async (token: string, payload: TemplateUploadPayload): Promise<TemplateResponse> => {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("name", payload.name);
    if (payload.description) formData.append("description", payload.description);
    formData.append("category", payload.category);
    formData.append("visibility", payload.visibility);
    if (payload.scope_organization) formData.append("scope_organization", payload.scope_organization);
    if (payload.scope_department) formData.append("scope_department", payload.scope_department);
    if (payload.allowed_roles?.length) formData.append("allowed_roles", payload.allowed_roles.join(","));
    return uploadForm<TemplateResponse>("/templates/upload", formData, token);
  },
};

/**
 * Every template endpoint in one object (catalog + preparation pipeline), so
 * existing `templatesApi.x(...)` call sites keep working.
 */
export const templatesApi = {
  ...templateCatalogApi,
  ...templatePipelineApi,
};

export const templateAccessApi = {
  getOptions: (token: string) =>
    request<TemplateAccessOptions>("/templates/access-options", {}, token),
  update: (token: string, id: number, body: TemplateAccessUpdate) =>
    request<TemplateResponse>(
      `/templates/${id}/access`,
      { method: "PATCH", body: JSON.stringify(body) },
      token,
    ),
};
