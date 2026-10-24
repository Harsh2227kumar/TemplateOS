import {
  refreshOutcomeFromStatus,
  sendWithRefresh,
  singleFlight,
  type RefreshOutcome,
} from "./refresh";
import { SESSION_EXPIRED_EVENT } from "./session";

// Production builds must set VITE_API_BASE_URL; without it they call the
// same-origin /api/v1 instead of silently targeting a developer's localhost.
// Keep "localhost" (not 127.0.0.1) in dev: the SPA runs on localhost:5173 and
// the session cookies are only sent to the same site.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000/api/v1" : "/api/v1");

/** Required by the backend's CSRF rule on POST/PUT/PATCH/DELETE; sent on every request. */
const CSRF_HEADER = "X-Requested-With";
const CSRF_HEADER_VALUE = "TemplateOS";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: any,
    /** Seconds from a Retry-After header (e.g. 429 on too many login attempts). */
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
  }
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds;
  const date = Date.parse(value);
  return Number.isNaN(date) ? undefined : Math.max(0, Math.round((date - Date.now()) / 1000));
}

/**
 * One raw fetch with the session cookies and the CSRF header. Never sends an
 * Authorization header: the backend does not fall back to the cookie when a
 * bearer token is present.
 */
function send(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set(CSRF_HEADER, CSRF_HEADER_VALUE);
  // FormData bodies get their multipart Content-Type (with boundary) from the browser.
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers, credentials: "include" });
}

/** POST /auth/refresh, shared by every request that hit a 401 at the same time. */
const refreshSession = singleFlight(async (): Promise<RefreshOutcome> => {
  try {
    const response = await send("/auth/refresh", { method: "POST" });
    return refreshOutcomeFromStatus(response.status);
  } catch {
    return "unavailable";
  }
});

/** Tell the auth context the session is over so ProtectedRoute sends the user to /login. */
function notifySessionExpired(): void {
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

async function toApiError(response: Response, fallback: string): Promise<ApiError> {
  let message = fallback;
  let detail: any = undefined;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = "Validation failed";
      detail = body.detail;
    } else if (body.detail && typeof body.detail === "object") {
      // V1.7 P2.1: coded conflicts, e.g. {"detail": "...", "code": "manual_edits", "version": 3}.
      if (typeof body.detail.detail === "string") message = body.detail.detail;
      detail = body.detail;
    }
  } catch {
    // Keep a safe user-facing fallback when the server does not return JSON.
  }
  return new ApiError(message, response.status, detail, parseRetryAfter(response.headers.get("Retry-After")));
}

async function execute<T>(path: string, options: RequestInit, fallbackMessage: string): Promise<T> {
  const response = await sendWithRefresh({
    path,
    send: () => send(path, options),
    refresh: refreshSession,
    onSessionExpired: notifySessionExpired,
  });
  if (!response.ok) throw await toApiError(response, fallbackMessage);
  // 204 No Content (e.g. DELETE endpoints) has no body to parse.
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** JSON request. A 401 refreshes the session once and repeats the request once. */
export function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return execute<T>(path, options, "Something went wrong. Please try again.");
}

export interface FileDownload {
  blob: Blob;
  /** Raw Content-Disposition header (null when CORS hides it). */
  contentDisposition: string | null;
}

/**
 * GET a file as a Blob with the session cookies (and the same 401 refresh),
 * so httpOnly-cookie auth works and errors (404/409 JSON) become ApiError.
 */
export async function requestFile(path: string): Promise<FileDownload> {
  const response = await sendWithRefresh({
    path,
    send: () => send(path),
    refresh: refreshSession,
    onSessionExpired: notifySessionExpired,
  });
  if (!response.ok) throw await toApiError(response, "Download failed. Please try again.");
  return { blob: await response.blob(), contentDisposition: response.headers.get("Content-Disposition") };
}

/** POST a multipart form (file uploads), with the same cookie/refresh handling. */
export function uploadForm<T>(path: string, formData: FormData): Promise<T> {
  return execute<T>(path, { method: "POST", body: formData }, "Upload failed. Please try again.");
}
