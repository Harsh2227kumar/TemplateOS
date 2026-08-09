const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

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
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep a safe user-facing fallback when the server does not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const authApi = {
  signup: (input: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  login: (input: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  me: (token: string) => request<User>("/auth/me", {}, token),
};

export interface TemplateResponse {
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
}

export const templatesApi = {
  upload: async (
    token: string,
    payload: {
      file: File;
      name: string;
      description?: string;
      category: string;
      visibility: string;
    },
  ): Promise<TemplateResponse> => {
    // Temporary mock — replace with real fetch when backend is ready
    await new Promise((res) => setTimeout(res, 2000));
    return {
      id: 1,
      name: payload.name,
      description: payload.description ?? null,
      category: payload.category,
      visibility: payload.visibility,
      status: "uploaded",
      original_file_path: "templates/original/mock-file.docx",
      original_filename: payload.file.name,
      file_size_bytes: payload.file.size,
      uploaded_by: 1,
      version: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    // ── Uncomment below and remove the mock above when Member 2's backend is ready ──
    //
    // const formData = new FormData();
    // formData.append("file", payload.file);
    // formData.append("name", payload.name);
    // if (payload.description) formData.append("description", payload.description);
    // formData.append("category", payload.category);
    // formData.append("visibility", payload.visibility);
    //
    // const response = await fetch(`${API_BASE_URL}/templates/upload`, {
    //   method: "POST",
    //   headers: { Authorization: `Bearer ${token}` },
    //   // Do NOT set Content-Type — browser sets it with the correct multipart boundary
    //   body: formData,
    // });
    //
    // if (!response.ok) {
    //   let message = "Upload failed. Please try again.";
    //   try {
    //     const body = (await response.json()) as { detail?: string };
    //     if (typeof body.detail === "string") message = body.detail;
    //   } catch { /* keep fallback */ }
    //   throw new ApiError(message, response.status);
    // }
    // return response.json() as Promise<TemplateResponse>;
  },
};
