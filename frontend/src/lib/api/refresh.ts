/**
 * Session refresh logic for cookie auth, kept free of browser globals, Vite
 * env access and `@/` imports so it can be unit tested with `node --test`
 * (see frontend/tests/refresh.test.ts).
 *
 * The access cookie lives 15 minutes. When a request comes back 401, the
 * client calls POST /auth/refresh once (shared by every request that failed
 * at the same time) and then repeats the original request once.
 */

/** Result of one refresh attempt. */
export type RefreshOutcome =
  /** New cookies were issued; the original request can be repeated. */
  | "refreshed"
  /** The server refused the refresh cookie (401/403): the session is over. */
  | "rejected"
  /** Network error or 5xx: the session may still be valid, so do not sign out. */
  | "unavailable";

/** Paths whose 401 must never trigger a refresh (they are the auth flow itself). */
const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

export function shouldRefreshAfter401(path: string): boolean {
  const pathname = path.split("?")[0];
  return !NO_REFRESH_PATHS.includes(pathname);
}

/**
 * Map the status of a POST /auth/refresh response to an outcome.
 *
 * 409 "Refresh token already rotated" means another tab refreshed a moment
 * ago and the browser already holds the new cookies: treat it as success.
 */
export function refreshOutcomeFromStatus(status: number): RefreshOutcome {
  if (status >= 200 && status < 300) return "refreshed";
  if (status === 409) return "refreshed";
  if (status === 401 || status === 403) return "rejected";
  return "unavailable";
}

/**
 * Wraps `task` so that concurrent callers share one in-flight promise. Once it
 * settles, the next call starts a new run.
 */
export function singleFlight<T>(task: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (!inFlight) {
      inFlight = task().finally(() => {
        inFlight = null;
      });
    }
    return inFlight;
  };
}

export interface RefreshingSendOptions<R extends { status: number }> {
  /** API path of the request, used to skip refresh for the auth endpoints. */
  path: string;
  /** Performs the request. Called at most twice. */
  send: () => Promise<R>;
  /** Refreshes the session; should be single-flight (see `singleFlight`). */
  refresh: () => Promise<RefreshOutcome>;
  /** Called when the refresh was rejected, i.e. the user must sign in again. */
  onSessionExpired: () => void;
}

/**
 * Sends a request; on 401 refreshes the session once and retries once. Returns
 * the last response (the caller turns non-2xx responses into errors).
 */
export async function sendWithRefresh<R extends { status: number }>({
  path,
  send,
  refresh,
  onSessionExpired,
}: RefreshingSendOptions<R>): Promise<R> {
  const response = await send();
  if (response.status !== 401 || !shouldRefreshAfter401(path)) return response;

  const outcome = await refresh();
  if (outcome === "refreshed") return send();
  if (outcome === "rejected") onSessionExpired();
  return response;
}
