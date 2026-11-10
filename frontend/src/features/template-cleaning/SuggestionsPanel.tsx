import { useState } from "react";
import { CheckCheck, ChevronDown, ChevronUp, RefreshCw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Notice } from "@/components/fields/pipeline-ui";
import { GROUP_META } from "@/lib/template-pipeline";

import { SuggestionCard } from "./SuggestionCard";
import type { CleaningSession } from "./use-cleaning-session";

interface SuggestionsPanelProps {
  session: CleaningSession;
  loading: boolean;
  error: string | null;
  onRescan: () => void;
}

/** LEFT column: automatic suggestions, grouped, with bulk accept/reject. */
export function SuggestionsPanel({ session, loading, error, onRescan }: SuggestionsPanelProps) {
  const { suggestionData, suggestions, grouped, decisions, accepted, highPending } = session;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [showRejected, setShowRejected] = useState(false);
  const highCount = suggestionData?.high_confidence_count ?? 0;

  return (
    <section className="min-w-0 space-y-4" aria-label="Suggestions">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            Suggested placeholders
          </CardTitle>
          <CardDescription>
            {loading
              ? "Analyzing the document…"
              : suggestionData
                ? `${suggestionData.suggestion_count} found · ${highCount} high-confidence · ${accepted.length} accepted`
                : "Spots in the document that look like they should be filled in."}
          </CardDescription>
          {suggestionData && suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-3">
              <Button
                size="sm"
                className="gap-1.5"
                disabled={highPending.length === 0}
                onClick={() => session.setStatus(highPending.map((s) => s.id), "accepted")}
              >
                <CheckCheck className="h-4 w-4" />
                Accept all high-confidence{highPending.length ? ` (${highPending.length})` : ""}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={accepted.length === 0 && !session.hasRejected}
                onClick={() => session.setStatus(suggestions.map((s) => s.id), "pending")}
              >
                Reset choices
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowRejected((v) => !v)}>
                {showRejected ? "Hide rejected" : "Show rejected"}
              </Button>
              <Button size="sm" variant="ghost" className="gap-1.5" disabled={loading} onClick={onRescan}>
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                Re-scan
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {loading && !suggestionData && (
            <div className="space-y-3" aria-label="Loading suggestions">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}
          {error && (
            <Notice
              tone="error"
              title="Could not analyze the document"
              action={
                <Button size="sm" variant="outline" onClick={onRescan}>
                  Try again
                </Button>
              }
            >
              {error} You can still select text in the document to create placeholders manually.
            </Notice>
          )}
          {suggestionData && suggestions.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-600">
              No automatic suggestions for this document
              {suggestionData.existing_placeholders.length > 0
                ? ` — it already has ${suggestionData.existing_placeholders.length} placeholder(s).`
                : "."}{" "}
              Select text in the document to create placeholders manually.
            </div>
          )}
        </CardContent>
      </Card>

      {grouped.map(({ group, items }) => {
        const meta = GROUP_META[group];
        const visibleItems = items.filter((s) => showRejected || decisions[s.id]?.status !== "rejected");
        const acceptedInGroup = items.filter((s) => decisions[s.id]?.status === "accepted").length;
        const collapsed = collapsedGroups[group];
        return (
          <Card key={group}>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <button
                  type="button"
                  className="flex min-w-0 items-center gap-2 text-left"
                  onClick={() => setCollapsedGroups((prev) => ({ ...prev, [group]: !collapsed }))}
                  aria-expanded={!collapsed}
                >
                  {collapsed ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronUp className="h-4 w-4 shrink-0" />}
                  <span className="font-semibold text-slate-900">{meta.title}</span>
                  <Badge variant="outline" className="bg-slate-50">
                    {acceptedInGroup}/{items.length}
                  </Badge>
                </button>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 text-xs"
                    onClick={() => session.setStatus(items.map((s) => s.id), "accepted")}
                  >
                    Accept all
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 text-xs text-slate-500"
                    onClick={() => session.setStatus(items.map((s) => s.id), "rejected")}
                  >
                    Reject all
                  </Button>
                </div>
              </div>
              <p className="text-xs text-slate-500">{meta.description}</p>
            </CardHeader>
            {!collapsed && (
              <CardContent className="space-y-3">
                {visibleItems.length === 0 && (
                  <p className="text-xs text-slate-400">All suggestions in this group were rejected.</p>
                )}
                {visibleItems.map((suggestion) => {
                  const decision = decisions[suggestion.id];
                  if (!decision) return null;
                  const isEditing = session.editingId === suggestion.id;
                  return (
                    <SuggestionCard
                      key={suggestion.id}
                      suggestion={suggestion}
                      decision={decision}
                      sharedCount={session.sharedKeyCount(decision.key)}
                      isEditing={isEditing}
                      isExpanded={Boolean(expanded[suggestion.id])}
                      onStatusChange={(status) => session.setStatus([suggestion.id], status)}
                      onDecisionChange={(patch) => session.updateDecision(suggestion.id, patch)}
                      onToggleEdit={() => session.setEditingId(isEditing ? null : suggestion.id)}
                      onToggleExpanded={() =>
                        setExpanded((prev) => ({ ...prev, [suggestion.id]: !prev[suggestion.id] }))
                      }
                    />
                  );
                })}
              </CardContent>
            )}
          </Card>
        );
      })}
    </section>
  );
}
