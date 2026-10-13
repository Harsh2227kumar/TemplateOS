// Run with `npm test`. Cookie-session refresh: single-flight + one retry.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  refreshOutcomeFromStatus,
  sendWithRefresh,
  shouldRefreshAfter401,
  singleFlight,
  type RefreshOutcome,
} from "../src/lib/api/refresh.ts";

const res = (status: number) => ({ status });

/** A deferred refresh so the test controls when it settles. */
function controlledRefresh() {
  let calls = 0;
  let resolve!: (outcome: RefreshOutcome) => void;
  const refresh = singleFlight(() => {
    calls += 1;
    return new Promise<RefreshOutcome>((r) => {
      resolve = r;
    });
  });
  return { refresh, settle: (o: RefreshOutcome) => resolve(o), calls: () => calls };
}

test("auth endpoints never trigger a refresh", () => {
  assert.equal(shouldRefreshAfter401("/auth/login"), false);
  assert.equal(shouldRefreshAfter401("/auth/refresh"), false);
  assert.equal(shouldRefreshAfter401("/auth/logout"), false);
  assert.equal(shouldRefreshAfter401("/auth/me"), true);
  assert.equal(shouldRefreshAfter401("/templates/3?force=true"), true);
});

test("refresh status maps to refreshed / rejected / unavailable", () => {
  assert.equal(refreshOutcomeFromStatus(200), "refreshed");
  assert.equal(refreshOutcomeFromStatus(204), "refreshed");
  assert.equal(refreshOutcomeFromStatus(401), "rejected");
  assert.equal(refreshOutcomeFromStatus(403), "rejected");
  assert.equal(refreshOutcomeFromStatus(500), "unavailable");
  assert.equal(refreshOutcomeFromStatus(503), "unavailable");
});

test("singleFlight shares one promise between concurrent callers, then resets", async () => {
  let runs = 0;
  const run = singleFlight(async () => {
    runs += 1;
    await new Promise((r) => setTimeout(r, 5));
    return runs;
  });
  const [a, b, c] = await Promise.all([run(), run(), run()]);
  assert.deepEqual([a, b, c], [1, 1, 1]);
  assert.equal(runs, 1);
  assert.equal(await run(), 2, "a settled flight starts a new run next time");
});

test("singleFlight resets after a rejection too", async () => {
  let runs = 0;
  const run = singleFlight(async () => {
    runs += 1;
    if (runs === 1) throw new Error("boom");
    return "ok";
  });
  await assert.rejects(run(), /boom/);
  assert.equal(await run(), "ok");
});

test("a 2xx response is returned without refreshing", async () => {
  let refreshed = 0;
  const response = await sendWithRefresh({
    path: "/templates/",
    send: async () => res(200),
    refresh: async () => {
      refreshed += 1;
      return "refreshed";
    },
    onSessionExpired: () => assert.fail("must not expire"),
  });
  assert.equal(response.status, 200);
  assert.equal(refreshed, 0);
});

test("401 -> refresh -> the original request is retried exactly once", async () => {
  const statuses = [401, 200];
  let sends = 0;
  const response = await sendWithRefresh({
    path: "/documents",
    send: async () => res(statuses[sends++]),
    refresh: async () => "refreshed",
    onSessionExpired: () => assert.fail("must not expire"),
  });
  assert.equal(response.status, 200);
  assert.equal(sends, 2);
});

test("a second 401 after a successful refresh is returned, not looped", async () => {
  let sends = 0;
  let refreshes = 0;
  const response = await sendWithRefresh({
    path: "/documents",
    send: async () => {
      sends += 1;
      return res(401);
    },
    refresh: async () => {
      refreshes += 1;
      return "refreshed";
    },
    onSessionExpired: () => {},
  });
  assert.equal(response.status, 401);
  assert.equal(sends, 2);
  assert.equal(refreshes, 1);
});

test("concurrent 401s share one refresh and each retries once", async () => {
  const { refresh, settle, calls } = controlledRefresh();
  const sendsByPath = new Map<string, number>();
  const make = (path: string) =>
    sendWithRefresh({
      path,
      send: async () => {
        const n = (sendsByPath.get(path) ?? 0) + 1;
        sendsByPath.set(path, n);
        return res(n === 1 ? 401 : 200);
      },
      refresh,
      onSessionExpired: () => assert.fail("must not expire"),
    });

  const pending = [make("/a"), make("/b"), make("/c")];
  // Let all three first sends resolve and join the refresh.
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(calls(), 1, "only one POST /auth/refresh");
  settle("refreshed");

  const responses = await Promise.all(pending);
  assert.deepEqual(responses.map((r) => r.status), [200, 200, 200]);
  assert.deepEqual([...sendsByPath.values()], [2, 2, 2]);
});

test("a rejected refresh expires the session once per request and returns the 401", async () => {
  let expired = 0;
  const response = await sendWithRefresh({
    path: "/auth/me",
    send: async () => res(401),
    refresh: async () => "rejected",
    onSessionExpired: () => {
      expired += 1;
    },
  });
  assert.equal(response.status, 401);
  assert.equal(expired, 1);
});

test("an unavailable refresh (network/5xx) does not sign the user out", async () => {
  let sends = 0;
  const response = await sendWithRefresh({
    path: "/templates/",
    send: async () => {
      sends += 1;
      return res(401);
    },
    refresh: async () => "unavailable",
    onSessionExpired: () => assert.fail("must not expire on a network error"),
  });
  assert.equal(response.status, 401);
  assert.equal(sends, 1, "no retry without new cookies");
});

test("401 from the login endpoint is returned as-is (wrong password)", async () => {
  const response = await sendWithRefresh({
    path: "/auth/login",
    send: async () => res(401),
    refresh: async () => assert.fail("must not refresh"),
    onSessionExpired: () => assert.fail("must not expire"),
  });
  assert.equal(response.status, 401);
});
