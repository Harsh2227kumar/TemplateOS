import { Check, Eye, Pencil, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfidenceBadge, MonoKey } from "@/components/fields/pipeline-ui";
import type { CleanSuggestion } from "@/lib/api";
import {
  FIELD_TYPE_OPTIONS,
  KEY_PATTERN,
  KEY_RULE_MESSAGE,
  fieldTypeLabel,
  keyToLabel,
  type FieldTypeValue,
} from "@/lib/template-pipeline";

import type { Decision, DecisionStatus } from "./cleaning-model";
import { SuggestionContextView } from "./HighlightedText";

interface SuggestionCardProps {
  suggestion: CleanSuggestion;
  decision: Decision;
  /** How many accepted suggestions share this key (one field fills them all). */
  sharedCount: number;
  isEditing: boolean;
  isExpanded: boolean;
  onStatusChange: (status: DecisionStatus) => void;
  onDecisionChange: (patch: Partial<Decision>) => void;
  onToggleEdit: () => void;
  onToggleExpanded: () => void;
}

export function SuggestionCard({
  suggestion,
  decision,
  sharedCount,
  isEditing,
  isExpanded,
  onStatusChange,
  onDecisionChange,
  onToggleEdit,
  onToggleExpanded,
}: SuggestionCardProps) {
  const isAccepted = decision.status === "accepted";
  const isRejected = decision.status === "rejected";
  const keyInvalid = !KEY_PATTERN.test(decision.key);

  return (
    <article
      className={`space-y-2 rounded-xl border p-3 transition-colors ${
        isAccepted
          ? "border-emerald-300 bg-emerald-50/40"
          : isRejected
            ? "border-slate-200 bg-slate-50 opacity-60"
            : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 break-words text-sm font-medium text-slate-900">
          {decision.label || keyToLabel(decision.key)}
        </span>
        <MonoKey name={decision.key} />
        <Badge variant="outline" className="bg-white">{fieldTypeLabel(decision.type)}</Badge>
        <ConfidenceBadge confidence={suggestion.confidence} />
        {suggestion.location !== "body" && (
          <Badge variant="outline" className="capitalize text-slate-500">
            {suggestion.location}
          </Badge>
        )}
        {isAccepted && sharedCount > 1 && (
          <span className="text-xs text-emerald-700">one field fills {sharedCount} spots</span>
        )}
      </div>
      <p className="text-xs text-slate-500">{suggestion.reason}</p>
      <SuggestionContextView suggestion={suggestion} />
      {isExpanded && suggestion.anchor.action !== "list" && (
        <p className="whitespace-pre-wrap break-words rounded-md border border-dashed border-slate-200 p-2 text-xs text-slate-600">
          {suggestion.context.paragraph_text}
        </p>
      )}

      {isEditing && (
        <div className="grid gap-2 rounded-lg border border-slate-200 bg-white p-2 sm:grid-cols-3">
          <label className="space-y-1 text-xs font-medium text-slate-600">
            Key
            <Input
              value={decision.key}
              aria-invalid={keyInvalid}
              className={`h-8 font-mono text-xs ${keyInvalid ? "border-red-400" : ""}`}
              onChange={(e) => onDecisionChange({ key: e.target.value.trim() })}
            />
          </label>
          <label className="space-y-1 text-xs font-medium text-slate-600">
            Label
            <Input
              value={decision.label}
              maxLength={150}
              className="h-8 text-xs"
              onChange={(e) => onDecisionChange({ label: e.target.value })}
            />
          </label>
          <div className="space-y-1 text-xs font-medium text-slate-600">
            Type
            <Select value={decision.type} onValueChange={(value) => onDecisionChange({ type: value as FieldTypeValue })}>
              <SelectTrigger className="h-8 text-xs" aria-label="Field type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-white text-slate-900">
                {FIELD_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
      {keyInvalid && <p className="text-xs text-red-600">{KEY_RULE_MESSAGE}.</p>}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={isAccepted ? "default" : "outline"}
          className="h-8 gap-1.5"
          aria-pressed={isAccepted}
          onClick={() => onStatusChange(isAccepted ? "pending" : "accepted")}
        >
          <Check className="h-3.5 w-3.5" />
          {isAccepted ? "Accepted" : "Accept"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-8 gap-1.5 text-slate-500"
          aria-pressed={isRejected}
          onClick={() => onStatusChange(isRejected ? "pending" : "rejected")}
        >
          <X className="h-3.5 w-3.5" />
          {isRejected ? "Undo reject" : "Reject"}
        </Button>
        <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onToggleEdit}>
          <Pencil className="h-3.5 w-3.5" />
          {isEditing ? "Done" : "Edit"}
        </Button>
        {suggestion.anchor.action !== "list" && (
          <Button size="sm" variant="ghost" className="h-8 gap-1.5 text-slate-500" onClick={onToggleExpanded}>
            <Eye className="h-3.5 w-3.5" />
            {isExpanded ? "Hide paragraph" : "Show paragraph"}
          </Button>
        )}
      </div>
    </article>
  );
}
