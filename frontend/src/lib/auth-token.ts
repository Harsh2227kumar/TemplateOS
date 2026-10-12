// Single place that knows where the access token lives. Storage access is
// wrapped because localStorage throws in some privacy modes.
const TOKEN_KEY = "templateos_access_token";

/** Fired on window when the API rejects the stored token (expired/revoked). */
export const SESSION_EXPIRED_EVENT = "templateos:session-expired";

export function getAccessToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAccessToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // The session then lasts only for this page load.
  }
}

export function clearAccessToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing stored to clear.
  }
}
