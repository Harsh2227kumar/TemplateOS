// Run with `npm test`. Page-level loading/error/retry built from several queries.
import { test } from "node:test";
import assert from "node:assert/strict";

import { combineQueries } from "../src/hooks/queries/combine.ts";
import { parseRouteId } from "../src/lib/route-params.ts";

function q(over: Partial<{ data: unknown; error: unknown; isError: boolean; isFetching: boolean }> = {}) {
  let refetches = 0;
  return {
    data: undefined as unknown,
    error: null as unknown,
    isError: false,
    isFetching: false,
    ...over,
    refetch: async () => {
      refetches += 1;
    },
    refetches: () => refetches,
  };
}

test("loading until every query has data", () => {
  const state = combineQueries([q({ data: 1 }), q({ isFetching: true })]);
  assert.equal(state.isLoading, true);
  assert.equal(state.isReady, false);
  assert.equal(state.error, null);
});

test("ready only when all data is there and nothing refetches", () => {
  assert.equal(combineQueries([q({ data: 1 }), q({ data: 2 })]).isReady, true);
  assert.equal(combineQueries([q({ data: 1 }), q({ data: 2, isFetching: true })]).isReady, false);
});

test("an error without data is reported once nothing is fetching", () => {
  const failed = q({ isError: true, error: { status: 500 } });
  assert.deepEqual(combineQueries([failed, q({ data: 1 })]).error, { status: 500 });
  assert.equal(combineQueries([failed, q({ isFetching: true })]).error, null, "wait for the other query");
});

test("a failed background refetch with cached data is not a page error", () => {
  const state = combineQueries([q({ data: 1, isError: true, error: { status: 500 } })]);
  assert.equal(state.error, null);
  assert.equal(state.isLoading, false);
});

test("retry refetches only the failed queries", () => {
  const ok = q({ data: 1 });
  const failed = q({ isError: true, error: new Error("x") });
  const disabled = q();
  combineQueries([ok, failed, disabled]).retry();
  assert.equal(ok.refetches(), 0);
  assert.equal(failed.refetches(), 1);
  assert.equal(disabled.refetches(), 0, "a disabled query is never forced");
});

test("route ids must be positive integers", () => {
  assert.equal(parseRouteId("42"), 42);
  assert.equal(parseRouteId("0"), null);
  assert.equal(parseRouteId("12abc"), null);
  assert.equal(parseRouteId("-3"), null);
  assert.equal(parseRouteId(undefined), null);
});
