import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { fieldNameFromHash } from "@/features/document-preview/preview-model";

/**
 * `#field-<name>` deep links (from the preview page's missing-field links):
 * once the form is ready, scroll that field into view and focus its input.
 * Runs once per hash so later re-renders never steal focus.
 */
export function useFocusFieldFromHash(ready: boolean) {
  const { hash } = useLocation();
  const handledRef = useRef<string | null>(null);

  useEffect(() => {
    const name = fieldNameFromHash(hash);
    if (!ready || !name || handledRef.current === hash) return;
    // Wait a frame so the seeded fields have rendered.
    const frame = requestAnimationFrame(() => {
      handledRef.current = hash;
      const container = document.querySelector<HTMLElement>(`[data-field-name="${CSS.escape(name)}"]`);
      if (!container) return;
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      container.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
      const focusable =
        container.querySelector<HTMLElement>(`#${CSS.escape(`field-${name}`)}`) ??
        container.querySelector<HTMLElement>("input, textarea, select, button:not([aria-disabled])");
      focusable?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [ready, hash]);
}
