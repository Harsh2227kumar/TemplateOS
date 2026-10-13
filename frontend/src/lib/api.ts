import { SESSION_EXPIRED_EVENT } from "@/lib/auth-token";

// Production builds must set VITE_API_BASE_URL; without it they call the
// same-origin /api/v1 instead of silently targeting a developer's localhost.
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000/api/v1" : "/api/v1");

/** Tell the auth context the stored token was rejected so it can sign out. */
function notifyIfSessionExpired(status: number, token?: string): void {
  if (status === 401 && token) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

export interface UserPreferences {
  default_document_format: string | null;
  email_notifications: boolean | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  department: string | null;
  organization: string | null;
  job_title: string | null;
  phone: string | null;
  avatar_url: string | null;
  signature_path: string | null;
  preferences: UserPreferences | null;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: any,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    notifyIfSessionExpired(response.status, token);
    let message = "Something went wrong. Please try again.";
    let detail: any = undefined;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = "Validation failed";
        detail = body.detail;
      }
    } catch {
      // Keep a safe user-facing fallback when the server does not return JSON.
    }
    throw new ApiError(message, response.status, detail);
  }
  // 204 No Content (e.g. DELETE endpoints) has no body to parse.
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const authApi = {
  signup: (input: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  login: (input: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  me: (token: string) => request<User>("/auth/me", {}, token),
};

export interface TemplateListItem extends TemplateAudience {
  id: number;
  name: string;
  category: string;
  visibility: string;
  status: string;
  uploaded_by: number;
  created_at: string;
}

export interface TemplateLibraryResponse {
  templates: TemplateListItem[];
  total: number;
  page: number;
  limit: number;
}

export interface TemplateResponse extends TemplateAudience {
  id: number;
  name: string;
  description: string | null;
  category: string;
  visibility: string;
  status: string;
  original_file_path: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  uploaded_by: number;
  version: number;
  created_at: string;
  updated_at: string;
  processed_file_path?: string | null;
}

// --- Template audience: organization / department scope + role restriction ---

export type TemplateVisibility = "private" | "public" | "organization" | "department" | "group";

export interface TemplateAudience {
  scope_organization: string | null;
  scope_department: string | null;
  /** null = every role in scope */
  allowed_roles: string[] | null;
  /** Computed by the server for the current user. */
  can_manage: boolean;
}

export interface TemplateAccessUpdate {
  visibility: TemplateVisibility;
  scope_organization?: string | null;
  scope_department?: string | null;
  allowed_roles?: string[] | null;
}

export interface TemplateAccessOptions {
  roles: { value: string; label: string }[];
  organizations: string[];
  departments: { organization: string | null; department: string }[];
  can_publish: { organization: boolean; department: boolean };
  defaults: { organization: string | null; department: string | null };
}

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

export interface TemplateField {
  id: number;
  template_id: number;
  field_name: string;
  field_label: string | null;
  field_type: string;
  default_value: string | null;
  is_required: boolean;
  description: string | null;
  example_value: string | null;
  validation_rule: string | null;
  section: string | null;
  ai_enabled: boolean;
  display_order: number;
  /** Provenance: detected | cleaned | manual | ai. */
  source?: string;
  created_at: string;
  updated_at: string;
}

export interface DetectionWarnings {
  duplicates: { key: string; count: number }[];
  invalid_names: { raw: string; suggested_key: string; count: number; reason: string }[];
  parse_error: string | null;
}

export interface PlaceholderDetectionResponse {
  template_id: number;
  status: string;
  already_detected: boolean;
  detected_fields: TemplateField[];
  warnings: DetectionWarnings;
  summary: {
    total_matches: number;
    unique_valid: number;
    invalid_count: number;
    duplicate_count: number;
  };
  /** "processed" when the cleaned copy was scanned. */
  source_file?: "original" | "processed";
  /** Keys created by this run (non-force re-runs only add new keys). */
  added_fields?: string[];
  /** Fields whose placeholder is no longer in the scanned document. */
  stale_fields?: string[];
}

export interface PlaceholderFix {
  raw: string;
  key: string;
}

// --- V1.3 Phase 3: field metadata editor ---

export interface TemplateFieldUpsert {
  id?: number;
  field_name: string;
  field_label?: string;
  field_type?: string;
  default_value?: string;
  is_required: boolean;
  description?: string;
  example_value?: string;
  validation_rule?: string;
  section?: string;
  ai_enabled: boolean;
}

export interface FieldSyncPayload {
  fields: TemplateFieldUpsert[];
  mark_configured?: boolean;
}

// --- V1.3 Phase 2: manual template cleaning ---

export interface DocSegment {
  index: number;
  location: "body" | "table" | "header" | "footer" | "textbox";
  text: string;
}

export interface TemplateContent {
  template_id: number;
  segments: DocSegment[];
  has_processed: boolean;
  source?: "original" | "processed";
}

/** Exact spot in the ORIGINAL document (from /clean-suggestions). */
export interface CleanAnchor {
  paragraph_id: number;
  start: number;
  end: number;
  action: "replace" | "insert" | "list";
  paragraph_ids?: number[];
}

export interface PlaceholderReplacement {
  /** Text to replace; may be empty for an anchored insert. */
  sample_text: string;
  placeholder_key: string;
  field_label?: string;
  field_type?: string;
  section?: string;
  segment_index?: number;
  anchor?: CleanAnchor;
  example_value?: string;
  validation_rule?: string;
  is_required?: boolean;
  ai_enabled?: boolean;
}

export type SuggestionGroup =
  | "fixes"
  | "lists"
  | "tables"
  | "blanks"
  | "brackets"
  | "empty_values"
  | "filled_values"
  | "detected_values";

export interface CleanSuggestion {
  id: string;
  kind: string;
  group: SuggestionGroup;
  placeholder_key: string;
  field_label: string;
  field_type: string;
  validation_rule: string | null;
  is_required: boolean;
  ai_enabled: boolean;
  section: string | null;
  example_value: string | null;
  confidence: number;
  high_confidence: boolean;
  reason: string;
  sample_text: string;
  location: DocSegment["location"];
  shared_key_count: number;
  anchor: CleanAnchor;
  context: { before: string; match: string; after: string; paragraph_text: string };
}

export interface CleanSuggestionsResponse {
  template_id: number;
  source: "original";
  has_processed: boolean;
  suggestion_count: number;
  high_confidence_count: number;
  high_confidence_threshold: number;
  existing_placeholders: string[];
  suggestions: CleanSuggestion[];
}

export interface ReplacementResult {
  placeholder_key: string;
  sample_text: string;
  occurrences: number;
  matched: boolean;
  reason?: string | null;
}

export interface CleanResponse {
  template_id: number;
  status: string;
  processed_file_path: string;
  created_fields: TemplateField[];
  results: ReplacementResult[];
  warnings: CleanWarnings;
  detected_keys?: string[];
}

export interface CleanWarnings {
  unmatched: string[];
  invalid_keys: string[];
  stale_fields?: string[];
  render_error?: string | null;
}

export interface CleanPreviewResponse {
  template_id: number;
  segments: DocSegment[];
  results: ReplacementResult[];
  warnings: CleanWarnings;
  detected_keys: string[];
}

export interface CleanTemplatePayload {
  replacements: PlaceholderReplacement[];
  confirm: boolean;
  mark_configured?: boolean;
}

// --- V1.3 Phase 4: AI field suggestions (proposals only — nothing persists here) ---

export interface FieldSuggestion {
  field_name: string;
  field_label: string | null;
  field_type: string;
  section: string | null;
  is_required: boolean;
  example_value: string | null;
  reason: string | null;
}

export interface SuggestFieldsResponse {
  template_id: number;
  model: string;
  existing_count: number;
  suggestion_count: number;
  suggestions: FieldSuggestion[];
}

// --- V1.4 Phase 1: Dynamic form rendering ---

export const templatesApi = {
  getLibrary: async (token: string, params?: {
    search?: string;
    category?: string;
    visibility?: string;
    status?: string;
    page?: number;
    limit?: number;
  }): Promise<TemplateLibraryResponse> => {
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

  deleteTemplate: async (token: string, id: number): Promise<void> => {
    return request<void>(`/templates/${id}`, { method: "DELETE" }, token);
  },

  upload: async (
    token: string,
    payload: {
      file: File;
      name: string;
      description?: string;
      category: string;
      visibility: string;
      scope_organization?: string;
      scope_department?: string;
      allowed_roles?: string[];
    },
  ): Promise<TemplateResponse> => {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("name", payload.name);
    if (payload.description) formData.append("description", payload.description);
    formData.append("category", payload.category);
    formData.append("visibility", payload.visibility);
    if (payload.scope_organization) formData.append("scope_organization", payload.scope_organization);
    if (payload.scope_department) formData.append("scope_department", payload.scope_department);
    if (payload.allowed_roles?.length) formData.append("allowed_roles", payload.allowed_roles.join(","));

    const response = await fetch(`${API_BASE_URL}/templates/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      // Do NOT set Content-Type — browser sets it with the correct multipart boundary
      body: formData,
    });

    if (!response.ok) {
      notifyIfSessionExpired(response.status, token);
      let message = "Upload failed. Please try again.";
      try {
        const body = (await response.json()) as { detail?: string };
        if (typeof body.detail === "string") message = body.detail;
      } catch { /* keep fallback */ }
      throw new ApiError(message, response.status);
    }
    return response.json() as Promise<TemplateResponse>;
  },
};

// --- V1.4 Phase 2: Document Drafts ---

export interface DocumentValue {
  id: number;
  document_id: number;
  field_name: string;
  value: string;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: number;
  template_id: number;
  created_by: number;
  name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  template_name?: string;
  values?: DocumentValue[];
}

export type DocumentFormValues = Record<string, any>;

export interface DocumentCreate {
  template_id: number;
  name?: string;
}

export interface DocumentValuesSave {
  values: Array<{ field_name: string; value: string }>;
}

export interface DocumentValuesResponse {
  document_id: number;
  values: DocumentValue[];
}

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

/**
 * Splits a 422 `detail` payload into errors that belong to rendered form fields
 * and messages that cannot be mapped to one. Supports both the app validator
 * format (`{field_name, error}`) and FastAPI/Pydantic request validation
 * (`{loc, msg, type}`). Returns null when `detail` is not an array.
 */
export function splitValidationErrors(
  detail: unknown,
  fieldNames: string[],
): { fieldErrors: Record<string, string>; otherMessages: string[] } | null {
  if (!Array.isArray(detail)) return null;
  const known = new Set(fieldNames);
  const fieldErrors: Record<string, string> = {};
  const otherMessages: string[] = [];

  for (const item of detail) {
    let name: string | undefined;
    let message: string | undefined;
    let location: string | undefined;

    if (item && typeof item === "object") {
      if (typeof item.field_name === "string") {
        name = item.field_name;
        location = item.field_name;
        message = typeof item.error === "string" ? item.error : typeof item.message === "string" ? item.message : undefined;
      } else if (Array.isArray(item.loc)) {
        const last = item.loc[item.loc.length - 1];
        if (typeof last === "string") name = last;
        location = item.loc.filter((part: unknown) => part !== "body").join(".");
        message = typeof item.msg === "string" ? item.msg : undefined;
      }
    }

    const text = message || "Invalid value";
    if (name && known.has(name)) {
      if (!fieldErrors[name]) fieldErrors[name] = text;
    } else {
      otherMessages.push(location ? `${location}: ${text}` : text);
    }
  }

  return { fieldErrors, otherMessages };
}

// --- V1.5 Phase 1: basic AI writing actions on a single field ---

export type AiTextAction = "grammar" | "tone" | "concise" | "formal";

// Matches the backend cap on original_text (MAX_IMPROVE_TEXT_CHARS).
export const MAX_AI_TEXT_CHARS = 5000;

export interface ImproveTextRequest {
  template_id: number;
  document_id?: number | null;
  field_name: string;
  original_text: string;
  action_type: AiTextAction;
}

export interface ImproveTextResponse {
  improved_text: string;
}

export const aiApi = {
  improveText: async (token: string, payload: ImproveTextRequest): Promise<ImproveTextResponse> => {
    return request<ImproveTextResponse>(
      "/ai/improve-text",
      { method: "POST", body: JSON.stringify(payload) },
      token,
    );
  },
};
