import { useLayoutEffect, useRef, useState } from "react";

const NOT_SEEDED = Symbol("not-seeded");

/**
 * Seeds local editing state (a react-hook-form `reset`, a draft copy) from
 * query data exactly once per `key` (e.g. the template or document id).
 *
 * Query data can change later — a background refetch, or an invalidation
 * after a save — and that must never overwrite what the user is editing, so
 * later changes are ignored. Pass `ready` = "data is loaded and not being
 * refetched" so a stale cache entry is not used as the starting point while a
 * fresh copy is on its way.
 *
 * Returns true once the state has been seeded for the current key.
 */
export function useSeedOnce<T>(
  key: unknown,
  data: T | undefined,
  ready: boolean,
  seed: (data: T) => void,
): boolean {
  const [seededKey, setSeededKey] = useState<unknown>(NOT_SEEDED);
  const seedRef = useRef(seed);
  seedRef.current = seed;

  const isSeeded = seededKey === key;

  // Layout effect: the seeded form is painted in the same frame as the data.
  useLayoutEffect(() => {
    if (isSeeded || !ready || data === undefined) return;
    seedRef.current(data);
    setSeededKey(key);
  }, [isSeeded, ready, data, key]);

  return isSeeded;
}
