import { request } from "./client";
import type { TokenResponse, User } from "./types";

export const authApi = {
  signup: (input: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  login: (input: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  me: (token: string) => request<User>("/auth/me", {}, token),
};
