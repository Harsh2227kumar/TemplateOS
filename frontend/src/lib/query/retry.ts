/**
 * Retry policy for queries: one retry for network errors and 5xx, never for a
 * 4xx (403/404/422 will not change by asking again; 401 is already handled by
 * the API client's refresh). Pure so it runs under `node --test`.
 */
export const MAX_QUERY_RETRIES = 1;

export function errorStatus(error: unknown): number | undefined {
  if (error && typeof error === "object" && "status" in error) {
    const status = (error as { status: unknown }).status;
    if (typeof status === "number") return status;
  }
  return undefined;
}

export function isClientError(error: unknown): boolean {
  const status = errorStatus(error);
  return status !== undefined && status >= 400 && status < 500;
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (isClientError(error)) return false;
  return failureCount < MAX_QUERY_RETRIES;
}
