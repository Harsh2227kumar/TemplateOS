interface QueryState {
  data: unknown;
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  refetch: () => Promise<unknown>;
}

export interface CombinedQueryState<E> {
  /** No data yet for at least one query (first load, or a retry after an error). */
  isLoading: boolean;
  /** The first error of a query that has no data, once nothing is fetching. */
  error: E | null;
  /** Every query has data and none is refetching: safe to seed a form. */
  isReady: boolean;
  /** Refetch the queries that failed (the "Retry" button). */
  retry: () => void;
}

/**
 * Combines the queries one page needs into the loading / error / retry shape
 * the pages had with Promise.all. A failed background refetch of a query that
 * already has data is not treated as a page error.
 */
export function combineQueries<E = Error>(queries: QueryState[]): CombinedQueryState<E> {
  const anyFetching = queries.some((q) => q.isFetching);
  const failed = queries.find((q) => q.isError && q.data === undefined);
  const error = failed && !anyFetching ? (failed.error as E) : null;
  const allData = queries.every((q) => q.data !== undefined);
  return {
    isLoading: !error && !allData,
    error,
    isReady: allData && !anyFetching,
    retry: () => {
      for (const q of queries) if (q.isError) void q.refetch();
    },
  };
}
