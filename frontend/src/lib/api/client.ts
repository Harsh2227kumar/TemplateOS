import { SESSION_EXPIRED_EVENT } from "@/lib/auth-token";

// Production builds must set VITE_API_BASE_URL; without it they call the
// same-origin /api/v1 instead of silently targeting a developer's localhost.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000/api/v1" : "/api/v1");

/** Tell the auth context the stored token was rejected so it can sign out. */
function notifyIfSessionExpired(status: number, token?: string): void {
  if (status === 401 && token) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
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

export async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
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

/** POST a multipart form (file uploads). The browser sets the multipart boundary. */
export async function uploadForm<T>(path: string, formData: FormData, token: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  return response.json() as Promise<T>;
}
