import { type ReactNode } from "react";
import { Briefcase, Loader2, Scissors, Sparkles, SpellCheck, Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { type AiTextAction } from "@/lib/api";

const ACTIONS: { type: AiTextAction; label: string; icon: ReactNode }[] = [
  { type: "grammar", label: "Fix grammar", icon: <SpellCheck className="h-3.5 w-3.5" /> },
  { type: "tone", label: "Professional", icon: <Briefcase className="h-3.5 w-3.5" /> },
  { type: "concise", label: "Concise", icon: <Scissors className="h-3.5 w-3.5" /> },
  { type: "formal", label: "Formal", icon: <Sparkles className="h-3.5 w-3.5" /> },
];

interface AiActionToolbarProps {
  onAction: (actionType: AiTextAction) => void;
  /** The action currently running, or null when idle. */
  loadingAction: AiTextAction | null;
  originalText: string;
  /** Shown after an AI replacement so the user can restore their text. */
  onUndo?: () => void;
}

/**
 * V1.5 Phase 1: AI writing actions rendered below an ai_enabled text or
 * textarea field. Buttons are disabled while a request runs or when the
 * field is empty.
 */
export function AiActionToolbar({ onAction, loadingAction, originalText, onUndo }: AiActionToolbarProps) {
  const isLoading = loadingAction !== null;
  const isEmpty = originalText.trim().length === 0;

  return (
    <div
      className="flex flex-wrap items-center gap-1.5 rounded-md border border-violet-200 bg-violet-50/60 px-2 py-1.5"
      role="toolbar"
      aria-label="AI writing actions"
    >
      <span className="mr-1 flex items-center gap-1 text-xs font-medium text-violet-700">
        <Sparkles className="h-3.5 w-3.5" />
        AI
      </span>
      {ACTIONS.map((action) => (
        <Button
          key={action.type}
          type="button"
          variant="ghost"
          size="sm"
          disabled={isLoading || isEmpty}
          onClick={() => onAction(action.type)}
          className="h-7 gap-1 px-2 text-xs text-violet-800 hover:bg-violet-100 hover:text-violet-900"
          title={isEmpty ? "Type some text first" : action.label}
        >
          {loadingAction === action.type ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            action.icon
          )}
          {action.label}
        </Button>
      ))}
      {onUndo && !isLoading && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onUndo}
          className="ml-auto h-7 gap-1 px-2 text-xs text-slate-600 hover:bg-slate-100"
        >
          <Undo2 className="h-3.5 w-3.5" />
          Undo
        </Button>
      )}
    </div>
  );
}
