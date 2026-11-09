// EkLink single sign-on helpers (see backend app/services/eklink.py).

/**
 * True when this page load came from the EkLink dashboard: EkLink sends its
 * origin as the referrer (Referrer-Policy strict-origin-when-cross-origin).
 * The SPA then signs in through EkLink so the session matches whoever is
 * signed in there.
 */
export function cameFromEklink(referrer: string, eklinkUrl: string | null | undefined): boolean {
  if (!referrer || !eklinkUrl) return false;
  try {
    return new URL(referrer).origin === new URL(eklinkUrl).origin;
  } catch {
    return false;
  }
}

