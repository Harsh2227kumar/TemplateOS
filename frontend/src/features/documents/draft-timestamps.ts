import { parseServerDate, serverTime } from "@/lib/dates";

/** The newest valid timestamp of a draft and its values ("Last saved"). */
export function latestTimestamp(times: Array<string | null | undefined>): string | null {
  let best: string | null = null;
  for (const t of times) {
    if (!t || !parseServerDate(t)) continue;
    if (best === null || serverTime(t) > serverTime(best)) best = t;
  }
  return best;
}
