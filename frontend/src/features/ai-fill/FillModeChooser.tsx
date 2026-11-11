import { Loader2, PencilLine, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type FillMode = "manual" | "ai";

const STORAGE_KEY = "templateos.fillMode";

/** The mode the user picked last time (a convenience only). */
export function rememberedFillMode(): FillMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "ai" ? "ai" : "manual";
  } catch {
    return "manual";
  }
}

export function rememberFillMode(mode: FillMode): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // Private window / blocked storage: nothing to remember.
  }
}

interface FillModeChooserProps {
  mode: FillMode;
  onModeChange: (mode: FillMode) => void;
  /** AI is configured on the server. */
  aiAvailable: boolean;
  /** The draft is being created for the assistant. */
  starting: boolean;
  disabled?: boolean;
  onStartAi: () => void;
  error?: string | null;
}

/**
 * V1.7 P2.2: how to fill a new document. "Fill the form myself" is the form
 * below; "Fill with AI assistant" creates the draft and opens the chat.
 */
export function FillModeChooser({
  mode,
  onModeChange,
  aiAvailable,
  starting,
  disabled = false,
  onStartAi,
  error,
}: FillModeChooserProps) {
  const options: Array<{ value: FillMode; title: string; text: string; icon: typeof Sparkles; unavailable?: string }> = [
    { value: "manual", title: "Fill the form myself", text: "Type each field yourself in the form below.", icon: PencilLine },
    {
      value: "ai",
      title: "Fill with AI assistant",
      text: "Tell the AI everything in your own words. It fills the form, fixes the language and asks about anything unclear. You can still edit every field.",
      icon: Sparkles,
      unavailable: aiAvailable ? undefined : "AI is not available right now",
    },
  ];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4" aria-labelledby="fill-mode-title">
      <h2 id="fill-mode-title" className="text-sm font-semibold text-slate-900">
        How do you want to fill this document?
      </h2>
      <div role="radiogroup" aria-labelledby="fill-mode-title" className="mt-3 grid gap-3 sm:grid-cols-2">
        {options.map(({ value, title, text, icon: Icon, unavailable }) => {
          const selected = mode === value;
          const off = disabled || starting || Boolean(unavailable);
          return (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors focus-within:ring-2 focus-within:ring-blue-500",
                selected ? "border-violet-400 bg-violet-50/60" : "border-slate-200 hover:bg-slate-50",
                off && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="radio"
                name="fill-mode"
                value={value}
                checked={selected}
                disabled={off}
                onChange={() => onModeChange(value)}
                className="sr-only"
              />
              <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", value === "ai" ? "text-violet-600" : "text-slate-500")} aria-hidden="true" />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-slate-900">{title}</span>
                <span className="mt-0.5 block text-xs leading-snug text-slate-600">{text}</span>
                {unavailable && <span className="mt-1 block text-xs font-medium text-amber-700">{unavailable}</span>}
              </span>
            </label>
          );
        })}
      </div>

      {mode === "ai" && aiAvailable && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500">A draft is created and the assistant opens next to the form.</p>
          <Button type="button" onClick={onStartAi} disabled={disabled || starting} className="w-full sm:w-auto">
            {starting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Opening the assistant…
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Start with the AI assistant
              </>
            )}
          </Button>
        </div>
      )}
      {error && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
