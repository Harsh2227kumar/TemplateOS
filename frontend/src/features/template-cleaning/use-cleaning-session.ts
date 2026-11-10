import { useCallback, useMemo, useState } from "react";

import type {
  CleanPreviewResponse,
  CleanSuggestion,
  CleanSuggestionsResponse,
  PlaceholderReplacement,
  SuggestionGroup,
} from "@/lib/api";
import { GROUP_ORDER, KEY_PATTERN, KEY_RULE_MESSAGE } from "@/lib/template-pipeline";

import { seedDecisions, type Decision, type DecisionStatus, type ManualReplacement } from "./cleaning-model";

/**
 * The user's cleaning choices: accepted/rejected suggestions (with edited
 * keys), manual placeholders and the last preview. Suggestions are a snapshot
 * taken on first load and on an explicit re-scan, so a background refetch of
 * the suggestions query never resets choices the user already made.
 */
export function useCleaningSession() {
  const [suggestionData, setSuggestionData] = useState<CleanSuggestionsResponse | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [manual, setManual] = useState<ManualReplacement[]>([]);
  const [preview, setPreview] = useState<CleanPreviewResponse | null>(null);

  const loadSuggestions = useCallback((data: CleanSuggestionsResponse) => {
    setSuggestionData(data);
    setDecisions(seedDecisions(data));
    setEditingId(null);
  }, []);

  const suggestions = useMemo(() => suggestionData?.suggestions ?? [], [suggestionData]);

  const grouped = useMemo(() => {
    const map = new Map<SuggestionGroup, CleanSuggestion[]>();
    for (const suggestion of suggestions) {
      const list = map.get(suggestion.group) ?? [];
      list.push(suggestion);
      map.set(suggestion.group, list);
    }
    return GROUP_ORDER.filter((group) => map.has(group)).map((group) => ({ group, items: map.get(group)! }));
  }, [suggestions]);

  const accepted = suggestions.filter((s) => decisions[s.id]?.status === "accepted");
  const highPending = suggestions.filter((s) => s.high_confidence && decisions[s.id]?.status === "pending");
  const hasRejected = suggestions.some((s) => decisions[s.id]?.status === "rejected");
  const invalidAccepted = accepted.filter((s) => !KEY_PATTERN.test(decisions[s.id]?.key ?? ""));

  const typeConflicts = useMemo(() => {
    const types = new Map<string, Set<string>>();
    for (const s of accepted) {
      const decision = decisions[s.id];
      if (!decision) continue;
      const set = types.get(decision.key) ?? new Set<string>();
      set.add(decision.type);
      types.set(decision.key, set);
    }
    for (const item of manual) {
      const set = types.get(item.placeholder_key) ?? new Set<string>();
      set.add(item.field_type ?? "text");
      types.set(item.placeholder_key, set);
    }
    return [...types.entries()].filter(([, set]) => set.size > 1).map(([key]) => key);
  }, [accepted, decisions, manual]);

  const changeCount = accepted.length + manual.length;

  const blockingProblem =
    changeCount === 0
      ? "Accept at least one suggestion or add a manual placeholder."
      : invalidAccepted.length > 0
        ? `Fix ${invalidAccepted.length} invalid key${invalidAccepted.length === 1 ? "" : "s"} first. ${KEY_RULE_MESSAGE}.`
        : null;

  const buildPayload = (): PlaceholderReplacement[] => [
    ...accepted.map((s) => {
      const decision = decisions[s.id];
      const keyChanged = decision.key !== s.placeholder_key;
      return {
        sample_text: s.sample_text,
        placeholder_key: decision.key,
        field_label: decision.label.trim() || undefined,
        field_type: decision.type,
        section: s.section ?? undefined,
        example_value: s.example_value ?? undefined,
        validation_rule: keyChanged ? undefined : s.validation_rule ?? undefined,
        is_required: s.is_required,
        ai_enabled: s.ai_enabled,
        anchor: s.anchor,
      };
    }),
    ...manual.map(({ id: _id, ...replacement }) => replacement),
  ];

  const setStatus = (ids: string[], status: DecisionStatus) => {
    setDecisions((prev) => {
      const next = { ...prev };
      for (const sid of ids) if (next[sid]) next[sid] = { ...next[sid], status };
      return next;
    });
    setPreview(null);
  };

  const updateDecision = (sid: string, patch: Partial<Decision>) => {
    setDecisions((prev) => ({ ...prev, [sid]: { ...prev[sid], ...patch } }));
    setPreview(null);
  };

  const addManual = (item: Omit<ManualReplacement, "id">) => {
    setManual((prev) => [...prev, { ...item, id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }]);
    setPreview(null);
  };

  const removeManual = (id: string) => {
    setManual((prev) => prev.filter((r) => r.id !== id));
    setPreview(null);
  };

  /** How many accepted suggestions use `key` (one field fills them all). */
  const sharedKeyCount = (key: string) => accepted.filter((s) => decisions[s.id]?.key === key).length;

  return {
    suggestionData,
    suggestions,
    grouped,
    decisions,
    accepted,
    highPending,
    hasRejected,
    typeConflicts,
    changeCount,
    blockingProblem,
    manual,
    preview,
    setPreview,
    editingId,
    setEditingId,
    loadSuggestions,
    buildPayload,
    setStatus,
    updateDecision,
    addManual,
    removeManual,
    sharedKeyCount,
  };
}

export type CleaningSession = ReturnType<typeof useCleaningSession>;
