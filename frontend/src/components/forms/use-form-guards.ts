import { useContext, useEffect, useRef } from "react";
import { UNSAFE_NavigationContext } from "react-router-dom";

const DEFAULT_LEAVE_MESSAGE = "You have unsaved changes. Leave this page and discard them?";

type PatchableNavigator = {
  push: (...args: unknown[]) => void;
  replace: (...args: unknown[]) => void;
  go: (delta: number) => void;
};

/**
 * Warns before leaving the page while `when` is true.
 *
 * - Closing/reloading the tab: the browser's own `beforeunload` prompt.
 * - In-app navigation (links, navigate(), navigate(-1)): a confirm dialog.
 *
 * react-router's `useBlocker` only works inside a data router
 * (createBrowserRouter); this app uses <BrowserRouter>, so the navigator is
 * wrapped instead, which is the documented v6 fallback. The browser's own
 * Back button is covered by `beforeunload` only when it leaves the app.
 */
export function useUnsavedChangesWarning(when: boolean, message = DEFAULT_LEAVE_MESSAGE) {
  const { navigator } = useContext(UNSAFE_NavigationContext);

  useEffect(() => {
    if (!when) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Required by some browsers to show the prompt.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    const nav = navigator as unknown as PatchableNavigator;
    const { push, replace, go } = nav;
    const confirmLeave = () => window.confirm(message);
    nav.push = (...args: unknown[]) => {
      if (confirmLeave()) push.apply(nav, args);
    };
    nav.replace = (...args: unknown[]) => {
      if (confirmLeave()) replace.apply(nav, args);
    };
    nav.go = (delta: number) => {
      if (delta === 0 || confirmLeave()) go.call(nav, delta);
    };

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      nav.push = push;
      nav.replace = replace;
      nav.go = go;
    };
  }, [when, message, navigator]);
}

/** Calls `onSave` on Ctrl+S / Cmd+S (instead of the browser's "Save page"). */
export function useSaveShortcut(onSave: () => void, enabled = true) {
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  useEffect(() => {
    if (!enabled) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (!event.repeat) onSaveRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled]);
}
