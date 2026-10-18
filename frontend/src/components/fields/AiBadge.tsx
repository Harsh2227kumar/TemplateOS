import { Sparkles } from "lucide-react";

import type { AiTextAction } from "@/lib/api";
import { cn } from "@/lib/utils";
import { AI_STYLE_LABELS } from "./use-ai-style-switcher";

/**
 * Small "AI" badge next to a field label: the value was written with AI and
 * not edited by hand since (V1.7 P2 ai_modified / ai_action).
 *
 * saved: the badge describes the saved value (preview, version view);
 * otherwise the value currently in the form (edit page).
 */
export function AiBadge({
  action,
  saved = true,
  className,
}: {
  action: AiTextAction | null;
  saved?: boolean;
  className?: string;
}) {
  const style = action ? AI_STYLE_LABELS[action] : null;
  const description = saved
    ? `Last saved value was written with AI${style ? ` (${style})` : ""}`
    : `Written with AI${style ? ` (${style})` : ""}; edit it to make it your own`;
  return (
    <span
      className={cn(
        "ml-1.5 inline-flex items-center gap-0.5 rounded-full border border-violet-200 bg-violet-50 px-1.5 py-px align-middle text-[10px] font-semibold tracking-wide text-violet-700",
        className,
      )}
      title={description}
    >
      <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
      AI
      <span className="sr-only">: {description}</span>
    </span>
  );
}
