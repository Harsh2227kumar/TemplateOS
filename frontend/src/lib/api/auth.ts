import { API_BASE_URL, request } from "./client";
import type { EklinkConfig, ProfileUpdate, TokenResponse, User } from "./types";

export const authApi = {
  signup: (input: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  /** Sets the httpOnly session cookies. The token in the body is not used by the SPA. */
  login: (input: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  eklinkConfig: () => request<EklinkConfig>("/auth/eklink"),
  /** Full-page navigation target: the backend sets a state cookie and redirects to EkLink. */
  eklinkLoginUrl: `${API_BASE_URL}/auth/eklink/login`,
  /** Exchanges EkLink's callback code; sets the session cookies like /login. */
  eklinkCallback: (input: { code: string; state: string }) =>
    request<TokenResponse>("/auth/eklink/callback", { method: "POST", body: JSON.stringify(input) }),
  me: () => request<User>("/auth/me"),
  /** Self-service: full_name, phone and job_title only. */
  updateMe: (body: ProfileUpdate) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(body) }),
  /** Clears the session cookies on the server. */
  logout: () => request<void>("/auth/logout", { method: "POST" }),
};
