import { useEffect, useState } from "react";

import { SLOW_PDF_HINT_MS, startSlowHintTimer } from "./generation";

/**
 * True once `active` has stayed true for `delayMs` (default 8 s). The timer
 * is cleared when `active` turns false (generation finished) and on unmount,
 * and the flag resets for the next run.
 */
export function useSlowHint(active: boolean, delayMs: number = SLOW_PDF_HINT_MS): boolean {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!active) {
      setSlow(false);
      return undefined;
    }
    return startSlowHintTimer(() => setSlow(true), delayMs);
  }, [active, delayMs]);

  return active && slow;
}
