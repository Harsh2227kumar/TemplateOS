/** Fired on window when the session cannot be refreshed (expired or revoked). */
export const SESSION_EXPIRED_EVENT = "templateos:session-expired";

// Auth used to keep a bearer token in localStorage under this key. Sessions
// are httpOnly cookies now, so the old value is only removed.
const LEGACY_TOKEN_KEY = "templateos_access_token";

/** Remove a token left behind by the old localStorage auth. Safe to call often. */
export function clearLegacyAccessToken(): void {
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    // localStorage throws in some privacy modes; nothing to clear then.
  }
}
