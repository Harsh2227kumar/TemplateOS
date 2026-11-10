import { QueryClient } from "@tanstack/react-query";

import { shouldRetryQuery } from "./retry";

export const DEFAULT_STALE_TIME_MS = 30_000;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Navigating back within 30s is served from cache without a request.
        staleTime: DEFAULT_STALE_TIME_MS,
        retry: shouldRetryQuery,
        // Most pages are forms; a refetch on focus must never touch them.
        refetchOnWindowFocus: false,
      },
      mutations: {
        // Saves, uploads and AI calls are not idempotent from the user's view.
        retry: false,
      },
    },
  });
}
