import { request } from "./client";
import type { ProfileUpdate, TokenResponse, User } from "./types";

export const authApi = {
  signup: (input: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  /** Sets the httpOnly session cookies. The token in the body is not used by the SPA. */
  login: (input: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  me: () => request<User>("/auth/me"),
  /** Self-service: full_name, phone and job_title only. */
  updateMe: (body: ProfileUpdate) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(body) }),
  /** Clears the session cookies on the server. */
  logout: () => request<void>("/auth/logout", { method: "POST" }),
};
