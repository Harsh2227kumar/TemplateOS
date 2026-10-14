import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Briefcase, Expand, Loader2, RotateCcw, Scissors, Sparkles, SpellCheck } from "lucide-react";

import { MAX_AI_TEXT_CHARS } from "@/lib/api";
import { cn } from "@/lib/utils";
import { styleAppliesTo, type AiFieldKind, type AiStyle } from "./ai-style-state";
import { AI_STYLE_LABELS, type AiStyleSwitcher } from "./use-ai-style-switcher";

export const AI_STYLES: { style: AiStyle; icon: ReactNode; hint: string }[] = [
  { style: "grammar", icon: <SpellCheck className="h-3.5 w-3.5" />, hint: "Fix spelling and grammar only" },
  { style: "tone", icon: <Briefcase className="h-3.5 w-3.5" />, hint: "Rewrite in a professional tone" },
  { style: "concise", icon: <Scissors className="h-3.5 w-3.5" />, hint: "Shorten while keeping the meaning" },
  { style: "formal", icon: <Sparkles className="h-3.5 w-3.5" />, hint: "Rewrite in formal language" },
  { style: "expand", icon: <Expand className="h-3.5 w-3.5" />, hint: "Expand into fuller sentences (no new facts)" },
];

interface AiActionToolbarProps {
  switcher: AiStyleSwitcher;
  /** Id of the input the toolbar acts on (for aria-controls). */
  controlsId: string;
  /** Whole form disabled (e.g. saving). */
  disabled?: boolean;
  /** The field's AI kind: lists are rewritten item by item; one-line inputs have no Expand. */
  kind?: AiFieldKind;
}

/**
 * Per-field AI style switcher. Each style is generated from the user's own
 * text (not from a previous AI result), the applied style is shown as
 * pressed, and "Original" restores the user's text. Keyboard: Tab enters the
 * toolbar, arrow keys / Home / End move between options, Enter or Space
 * applies one.
 */
export function AiActionToolbar({ switcher, controlsId, disabled = false, kind = "multiline" }: AiActionToolbarProps) {
  const { state, isPending, sourceLength, announcement } = switcher;
  const STYLES = AI_STYLES.filter(({ style }) => styleAppliesTo(style, kind));
  const isList = kind === "list";
  const [focusIndex, setFocusIndex] = useState(0);
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const isEmpty = switcher.fieldText.trim().length === 0;
  const isTooLong = sourceLength > MAX_AI_TEXT_CHARS;
  const hasApplied = state.applied !== null;
  const appliedStyle = state.applied?.style ?? null;
  const pendingStyle = state.pending?.style ?? null;

  // Index 0 is "Original", 1..n are the styles.
  const optionCount = STYLES.length + 1;

  const moveFocus = (index: number) => {
    const next = (index + optionCount) % optionCount;
    setFocusIndex(next);
    buttonRefs.current[next]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        moveFocus(focusIndex + 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        moveFocus(focusIndex - 1);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(0);
        break;
      case "End":
        event.preventDefault();
        moveFocus(optionCount - 1);
        break;
    }
  };

  let status: ReactNode;
  if (pendingStyle) {
    status = (
      <>
        Rewriting as <strong>{AI_STYLE_LABELS[pendingStyle]}</strong>… the field is locked until it finishes.
      </>
    );
  } else if (isTooLong) {
    status = (
      <span className="text-red-600">
        AI works on up to {MAX_AI_TEXT_CHARS.toLocaleString()} characters ({sourceLength.toLocaleString()} now).
      </span>
    );
  } else if (appliedStyle) {
    status = (
      <>
        <strong>{AI_STYLE_LABELS[appliedStyle]}</strong> applied. Every style starts from your original text, so
        switch freely. Editing the text makes it your new original.
      </>
    );
  } else if (isEmpty) {
    status = isList ? "Add some items, then pick a style." : "Type some text, then pick a style.";
  } else if (isList) {
    status = "Pick a style to rewrite each item. The number of items stays the same, and you can go back to the original.";
  } else {
    status = "Pick a style to rewrite your text. You can always go back to the original.";
  }

  // aria-disabled (not `disabled`) keeps keyboard focus on the clicked button
  // while a request runs, instead of dropping it to <body>.
  const renderButton = (
    index: number,
    key: string,
    content: ReactNode,
    opts: { pressed: boolean; unavailable: boolean; title: string; onClick: () => void; loading?: boolean },
  ) => (
    <button
      key={key}
      ref={(el) => {
        buttonRefs.current[index] = el;
      }}
      type="button"
      tabIndex={index === focusIndex ? 0 : -1}
      aria-pressed={opts.pressed}
      aria-disabled={opts.unavailable || undefined}
      aria-controls={controlsId}
      title={opts.title}
      onFocus={() => setFocusIndex(index)}
      onClick={() => {
        if (!opts.unavailable) opts.onClick();
      }}
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-1",
        opts.pressed
          ? "border-violet-600 bg-violet-600 text-white shadow-sm"
          : "border-violet-200 bg-white text-violet-800 hover:border-violet-300 hover:bg-violet-100",
        opts.unavailable && !opts.pressed && !opts.loading && "cursor-not-allowed opacity-50 hover:bg-white",
        opts.loading && "cursor-progress border-violet-400 bg-violet-100",
      )}
    >
      {content}
    </button>
  );

  return (
    <div className="rounded-md border border-violet-200 bg-violet-50/60 px-2 py-2">
      <div
        role="toolbar"
        aria-label="AI writing style"
        aria-busy={isPending}
        onKeyDown={handleKeyDown}
        className="flex flex-wrap items-center gap-1.5"
      >
        <span className="mr-0.5 flex items-center gap-1 text-xs font-semibold text-violet-700" aria-hidden="true">
          <Sparkles className="h-3.5 w-3.5" />
          AI style
        </span>
        {renderButton(
          0,
          "original",
          <>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Original
          </>,
          {
            pressed: !hasApplied && !isEmpty,
            unavailable: disabled || isPending || !hasApplied,
            title: hasApplied ? "Undo AI changes and restore your text" : "Your own text is shown",
            onClick: switcher.revert,
          },
        )}
        {STYLES.map(({ style, icon, hint }, i) => {
          const isLoading = pendingStyle === style;
          const pressed = appliedStyle === style;
          const unavailable = disabled || isPending || isEmpty || isTooLong;
          const title = isEmpty
            ? isList
              ? "Add an item first"
              : "Type some text first"
            : isTooLong
              ? `Text is over ${MAX_AI_TEXT_CHARS.toLocaleString()} characters`
              : pressed
                ? `${hint} (click again for another version)`
                : hint;
          return renderButton(
            i + 1,
            style,
            <>
              {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : icon}
              {AI_STYLE_LABELS[style]}
            </>,
            { pressed, unavailable, title, onClick: () => switcher.runStyle(style), loading: isLoading },
          );
        })}
      </div>
      <p className="mt-1.5 text-xs leading-snug text-violet-900/80">{status}</p>
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>
    </div>
  );
}
