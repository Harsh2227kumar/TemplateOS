import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eraser,
  Eye,
  Loader2,
  MousePointerClick,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ConfidenceBadge,
  MonoKey,
  Notice,
  PipelineLoadError,
  PipelineSteps,
} from "@/components/fields/pipeline-ui";
import {
  templatesApi,
  type CleanPreviewResponse,
  type CleanResponse,
  type CleanSuggestion,
  type CleanSuggestionsResponse,
  type DocSegment,
  type PlaceholderReplacement,
  type SuggestionGroup,
  type TemplateContent,
} from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import { getAccessToken } from "@/lib/auth-token";
import {
  FIELD_TYPE_OPTIONS,
  FIELD_TYPE_VALUES,
  GROUP_META,
  GROUP_ORDER,
  KEY_PATTERN,
  KEY_RULE_MESSAGE,
  canManageTemplate,
  fieldTypeLabel,
  keyToLabel,
  pipelineErrorMessage,
  suggestKey,
  type FieldTypeValue,
  type ManagedTemplate,
} from "@/lib/template-pipeline";

const LOCATION_ORDER: DocSegment["location"][] = ["body", "table", "textbox", "header", "footer"];
const LOCATION_LABEL: Record<DocSegment["location"], string> = {
  body: "Body",
  table: "Tables",
  textbox: "Text boxes",
  header: "Header",
  footer: "Footer",
};
const MAX_SELECTION = 255;

const convertSchema = z.object({
  placeholder_key: z
    .string()
    .trim()
    .min(1, "Placeholder key is required")
    .max(100, "Placeholder key must be 100 characters or fewer")
    .regex(KEY_PATTERN, KEY_RULE_MESSAGE),
  field_label: z.string().max(150, "Label must be 150 characters or fewer").optional(),
  field_type: z.enum(FIELD_TYPE_VALUES),
  section: z.string().max(100, "Section must be 100 characters or fewer").optional(),
});
type ConvertValues = z.infer<typeof convertSchema>;

type DecisionStatus = "pending" | "accepted" | "rejected";
interface Decision {
  status: DecisionStatus;
  key: string;
  label: string;
  type: FieldTypeValue;
}

interface ManualReplacement extends PlaceholderReplacement {
  id: string;
}

/** Render text with {{ placeholders }} highlighted. */
function HighlightedText({ text }: { text: string }) {
  const parts = text.split(/(\{\{.*?\}\}|\{%.*?%\})/g);
  return (
    <>
      {parts.map((part, index) =>
        /^\{[{%]/.test(part) ? (
          <mark key={index} className="rounded bg-indigo-100 px-0.5 font-mono text-indigo-800">
            {part}
          </mark>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function visible(text: string): string {
  return text.replace(/\t/g, " ⇥ ");
}

function SuggestionContextView({ suggestion }: { suggestion: CleanSuggestion }) {
  if (suggestion.anchor.action === "list") {
    return (
      <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-600">
        {suggestion.sample_text.split("\n").map((item, index) => (
          <li key={index}>{item.trim() || <span className="italic text-slate-400">(empty item)</span>}</li>
        ))}
      </ul>
    );
  }
  const { before, after } = suggestion.context;
  const match = suggestion.sample_text;
  return (
    <p className="whitespace-pre-wrap break-words rounded-md bg-slate-50 px-2 py-1.5 font-mono text-xs leading-relaxed text-slate-600">
      {before && <span>{before.length >= 60 ? "…" : ""}{visible(before)}</span>}
      {match ? (
        <mark className="rounded bg-amber-100 px-0.5 text-amber-900 line-through decoration-amber-500/60">
          {visible(match)}
        </mark>
      ) : (
        <span className="mx-0.5 rounded bg-emerald-100 px-1 text-emerald-800">＋</span>
      )}
      {after && <span>{visible(after)}{after.length >= 60 ? "…" : ""}</span>}
    </p>
  );
}

export function TemplateCleaningPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const templateId = Number(id);

  const [template, setTemplate] = useState<ManagedTemplate | null>(null);
  const [content, setContent] = useState<TemplateContent | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ message: string; status?: number } | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [suggestionData, setSuggestionData] = useState<CleanSuggestionsResponse | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [showRejected, setShowRejected] = useState(false);

  const [manual, setManual] = useState<ManualReplacement[]>([]);
  const [selectedText, setSelectedText] = useState("");
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [convertOpen, setConvertOpen] = useState(false);
  const documentRef = useRef<HTMLDivElement>(null);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<CleanPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [applyOpen, setApplyOpen] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<CleanResponse | null>(null);

  const canManage = canManageTemplate(template, user);

  // ── loading ───────────────────────────────────────────────────────
  useEffect(() => {
    let active = true;
    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const token = getAccessToken();
        const [templateData, contentData] = await Promise.all([
          templatesApi.getTemplateDetail(token, templateId),
          templatesApi.getContent(token, templateId),
        ]);
        if (!active) return;
        setTemplate(templateData);
        setContent(contentData);
      } catch (err: any) {
        if (!active) return;
        setLoadError({ message: err.message || "Failed to load template", status: err.status });
      } finally {
        if (active) setIsLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [templateId, reloadToken]);

  const loadSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    setSuggestionsError(null);
    try {
      const data = await templatesApi.getCleanSuggestions(getAccessToken(), templateId);
      setSuggestionData(data);
      setDecisions(
        Object.fromEntries(
          data.suggestions.map((s) => [
            s.id,
            {
              status: "pending" as DecisionStatus,
              key: s.placeholder_key,
              label: s.field_label,
              type: FIELD_TYPE_VALUES.includes(s.field_type as FieldTypeValue)
                ? (s.field_type as FieldTypeValue)
                : "text",
            },
          ]),
        ),
      );
      setEditingId(null);
    } catch (err: any) {
      setSuggestionsError(pipelineErrorMessage(err, "clean this template"));
    } finally {
      setSuggestionsLoading(false);
    }
  }, [templateId]);

  useEffect(() => {
    if (template && canManage && !suggestionData && !suggestionsLoading && !suggestionsError) {
      loadSuggestions();
    }
  }, [template, canManage, suggestionData, suggestionsLoading, suggestionsError, loadSuggestions]);

  // ── derived ───────────────────────────────────────────────────────
  const suggestions = suggestionData?.suggestions ?? [];

  const grouped = useMemo(() => {
    const map = new Map<SuggestionGroup, CleanSuggestion[]>();
    for (const suggestion of suggestions) {
      const list = map.get(suggestion.group) ?? [];
      list.push(suggestion);
      map.set(suggestion.group, list);
    }
    return GROUP_ORDER.filter((group) => map.has(group)).map((group) => ({
      group,
      items: map.get(group)!,
    }));
  }, [suggestions]);

  const accepted = suggestions.filter((s) => decisions[s.id]?.status === "accepted");
  const highPending = suggestions.filter(
    (s) => s.high_confidence && decisions[s.id]?.status === "pending",
  );

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

  const segmentsByLocation = useMemo(() => {
    const groupedSegments: Partial<Record<DocSegment["location"], DocSegment[]>> = {};
    for (const segment of content?.segments ?? []) {
      (groupedSegments[segment.location] ??= []).push(segment);
    }
    return groupedSegments;
  }, [content]);

  const changeCount = accepted.length + manual.length;

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

  // ── decisions ─────────────────────────────────────────────────────
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

  // ── manual selection ─────────────────────────────────────────────
  const handleSelection = () => {
    if (convertOpen) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    const anchorElement = selection.anchorNode?.parentElement ?? null;
    if (!anchorElement || !documentRef.current?.contains(anchorElement)) return;
    const text = selection.toString().trim();
    if (!text) return;
    if (text.length > MAX_SELECTION) {
      setSelectedText("");
      setSelectionNotice(`Select at most ${MAX_SELECTION} characters — that selection was ${text.length}.`);
      return;
    }
    setSelectionNotice(null);
    setSelectedText(text);
  };

  const form = useForm<ConvertValues>({
    resolver: zodResolver(convertSchema),
    defaultValues: { placeholder_key: "", field_label: "", field_type: "text", section: "" },
  });

  const openConvertDialog = () => {
    const key = suggestKey(selectedText).slice(0, 60);
    form.reset({
      placeholder_key: key,
      field_label: key ? keyToLabel(key) : "",
      field_type: "text",
      section: "",
    });
    setConvertOpen(true);
  };

  const stageManual = (values: ConvertValues) => {
    const key = values.placeholder_key.trim();
    if (manual.some((r) => r.sample_text === selectedText)) {
      form.setError("placeholder_key", { message: "This text is already staged" });
      return;
    }
    setManual((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        sample_text: selectedText,
        placeholder_key: key,
        field_label: values.field_label?.trim() || undefined,
        field_type: values.field_type,
        section: values.section?.trim() || undefined,
      },
    ]);
    setPreview(null);
    setConvertOpen(false);
    setSelectedText("");
    window.getSelection()?.removeAllRanges();
  };

  // ── preview + apply ──────────────────────────────────────────────
  const blockingProblem =
    changeCount === 0
      ? "Accept at least one suggestion or add a manual placeholder."
      : invalidAccepted.length > 0
        ? `Fix ${invalidAccepted.length} invalid key${invalidAccepted.length === 1 ? "" : "s"} first. ${KEY_RULE_MESSAGE}.`
        : null;

  const runPreview = async () => {
    if (blockingProblem || previewLoading) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const data = await templatesApi.previewClean(getAccessToken(), templateId, {
        replacements: buildPayload(),
        confirm: false,
      });
      setPreview(data);
    } catch (err: any) {
      setPreviewError(pipelineErrorMessage(err, "clean this template"));
    } finally {
      setPreviewLoading(false);
    }
  };

  const applyCleaning = async () => {
    if (isApplying || blockingProblem) return;
    setIsApplying(true);
    setActionError(null);
    try {
      const response = await templatesApi.cleanTemplate(getAccessToken(), templateId, {
        replacements: buildPayload(),
        confirm: true,
      });
      setApplyOpen(false);
      setResult(response);
      window.scrollTo({ top: 0 });
    } catch (err: any) {
      setApplyOpen(false);
      setActionError(pipelineErrorMessage(err, "clean this template"));
    } finally {
      setIsApplying(false);
    }
  };

  // ── views ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="max-w-6xl space-y-6">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-5 w-full max-w-md" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-96 w-full rounded-2xl" />
          <Skeleton className="h-96 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  if (loadError || !template || !content) {
    return (
      <PipelineLoadError
        status={loadError?.status}
        message={loadError?.message}
        onBack={() => navigate("/templates")}
        onRetry={() => setReloadToken((n) => n + 1)}
      />
    );
  }

  if (!canManage) {
    return (
      <div className="mx-auto max-w-xl space-y-4 px-2 py-16 text-center">
        <h2 className="text-2xl font-semibold">Only template managers can clean this template</h2>
        <p className="text-sm text-slate-600">
          Cleaning turns sample text into placeholders, so it is limited to people who manage
          this template.
        </p>
        <Button variant="outline" onClick={() => navigate(`/templates/${template.id}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
      </div>
    );
  }

  if (result) {
    const created = result.created_fields.length;
    const stale = result.warnings.stale_fields ?? [];
    return (
      <div className="max-w-4xl space-y-6 pb-10">
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={1} />
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Cleaning applied</h1>
          <p className="mt-2 text-sm text-slate-600">
            {template.name} · Status:{" "}
            <span className="font-medium capitalize">{result.status.replace(/_/g, " ")}</span>
          </p>
        </div>

        <Notice tone="success" title={`Processed template saved. ${created} new ${created === 1 ? "field" : "fields"}.`}>
          The original file is unchanged. The processed copy now has{" "}
          {result.detected_keys?.length ?? 0} placeholder
          {(result.detected_keys?.length ?? 0) === 1 ? "" : "s"} and is what documents will be
          generated from.
        </Notice>

        {result.warnings.render_error && (
          <Notice tone="error" title="The cleaned template may not render">
            {result.warnings.render_error}
          </Notice>
        )}
        {result.warnings.unmatched.length > 0 && (
          <Notice tone="warning" title="Some replacements were not applied">
            <ul className="list-disc space-y-0.5 pl-5">
              {result.results
                .filter((r) => !r.matched && r.reason !== "invalid_key")
                .map((r, index) => (
                  <li key={index}>
                    <MonoKey name={r.placeholder_key} />{" "}
                    {r.sample_text ? <span className="font-mono text-xs">“{r.sample_text}”</span> : null} —{" "}
                    {r.reason === "overlaps_another_replacement"
                      ? "overlaps another replacement"
                      : r.reason === "sample_text_not_found"
                        ? "text not found in the document"
                        : "the document no longer matches this spot"}
                  </li>
                ))}
            </ul>
          </Notice>
        )}
        {stale.length > 0 && (
          <Notice tone="warning" title="Fields without a placeholder">
            {stale.map((key) => <MonoKey key={key} name={key} className="mr-1" />)} no longer appear in
            the document. Remove them in Field Setup if they are not needed.
          </Notice>
        )}

        {created > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>New fields</CardTitle>
              <CardDescription>Metadata was inferred from each spot — review it in Field Setup.</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y divide-slate-100">
                {result.created_fields.map((field) => (
                  <li key={field.id} className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-6">
                    <span className="font-medium text-slate-900">{field.field_label || field.field_name}</span>
                    <MonoKey name={field.field_name} />
                    <Badge variant="outline" className="bg-slate-50">{fieldTypeLabel(field.field_type)}</Badge>
                    {field.section && <Badge variant="outline">{field.section}</Badge>}
                    {field.example_value && (
                      <span className="min-w-0 truncate text-xs text-slate-500">was: {field.example_value}</span>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap gap-3 border-t pt-6">
          <Button className="gap-2" onClick={() => navigate(`/templates/${template.id}/placeholders`)}>
            Review placeholders
            <ArrowRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" onClick={() => navigate(`/templates/${template.id}/fields`)}>
            Field Setup
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setResult(null);
              setPreview(null);
              setReloadToken((n) => n + 1);
            }}
          >
            Clean again
          </Button>
        </div>
      </div>
    );
  }

  const highCount = suggestionData?.high_confidence_count ?? 0;

  return (
    <div className="max-w-7xl space-y-6 pb-4">
      <div className="space-y-3">
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={1} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold sm:text-3xl">Template Cleaning</h1>
            <p className="mt-2 text-sm text-slate-600">
              {template.name} · Turn sample values and blanks into{" "}
              <span className="font-mono text-xs">{"{{ placeholders }}"}</span>. Your original file is
              never modified.
            </p>
          </div>
          {content.has_processed && (
            <Badge variant="outline" className="w-fit shrink-0 bg-blue-50 text-blue-700">
              A cleaned copy exists — applying replaces it
            </Badge>
          )}
        </div>
      </div>

      {actionError && (
        <Notice tone="error" title="Cleaning failed">
          {actionError}
        </Notice>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* LEFT — automatic suggestions */}
        <section className="min-w-0 space-y-4" aria-label="Suggestions">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-500" />
                Suggested placeholders
              </CardTitle>
              <CardDescription>
                {suggestionsLoading
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
                    onClick={() => setStatus(highPending.map((s) => s.id), "accepted")}
                  >
                    <CheckCheck className="h-4 w-4" />
                    Accept all high-confidence{highPending.length ? ` (${highPending.length})` : ""}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={accepted.length === 0 && !suggestions.some((s) => decisions[s.id]?.status === "rejected")}
                    onClick={() => setStatus(suggestions.map((s) => s.id), "pending")}
                  >
                    Reset choices
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowRejected((v) => !v)}>
                    {showRejected ? "Hide rejected" : "Show rejected"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="gap-1.5"
                    disabled={suggestionsLoading}
                    onClick={loadSuggestions}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${suggestionsLoading ? "animate-spin" : ""}`} />
                    Re-scan
                  </Button>
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {suggestionsLoading && !suggestionData && (
                <div className="space-y-3" aria-label="Loading suggestions">
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-24 w-full" />
                </div>
              )}
              {suggestionsError && (
                <Notice
                  tone="error"
                  title="Could not analyze the document"
                  action={
                    <Button size="sm" variant="outline" onClick={loadSuggestions}>
                      Try again
                    </Button>
                  }
                >
                  {suggestionsError} You can still select text in the document to create placeholders manually.
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
            const visibleItems = items.filter(
              (s) => showRejected || decisions[s.id]?.status !== "rejected",
            );
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
                        onClick={() => setStatus(items.map((s) => s.id), "accepted")}
                      >
                        Accept all
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 text-xs text-slate-500"
                        onClick={() => setStatus(items.map((s) => s.id), "rejected")}
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
                      const isAccepted = decision.status === "accepted";
                      const isRejected = decision.status === "rejected";
                      const keyInvalid = !KEY_PATTERN.test(decision.key);
                      const isEditing = editingId === suggestion.id;
                      const shared = accepted.filter((s) => decisions[s.id]?.key === decision.key).length;
                      return (
                        <article
                          key={suggestion.id}
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
                            {isAccepted && shared > 1 && (
                              <span className="text-xs text-emerald-700">one field fills {shared} spots</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500">{suggestion.reason}</p>
                          <SuggestionContextView suggestion={suggestion} />
                          {expanded[suggestion.id] && suggestion.anchor.action !== "list" && (
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
                                  onChange={(e) => updateDecision(suggestion.id, { key: e.target.value.trim() })}
                                />
                              </label>
                              <label className="space-y-1 text-xs font-medium text-slate-600">
                                Label
                                <Input
                                  value={decision.label}
                                  maxLength={150}
                                  className="h-8 text-xs"
                                  onChange={(e) => updateDecision(suggestion.id, { label: e.target.value })}
                                />
                              </label>
                              <div className="space-y-1 text-xs font-medium text-slate-600">
                                Type
                                <Select
                                  value={decision.type}
                                  onValueChange={(value) => updateDecision(suggestion.id, { type: value as FieldTypeValue })}
                                >
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
                          {keyInvalid && (
                            <p className="text-xs text-red-600">{KEY_RULE_MESSAGE}.</p>
                          )}

                          <div className="flex flex-wrap items-center gap-2">
                            <Button
                              size="sm"
                              variant={isAccepted ? "default" : "outline"}
                              className="h-8 gap-1.5"
                              aria-pressed={isAccepted}
                              onClick={() => setStatus([suggestion.id], isAccepted ? "pending" : "accepted")}
                            >
                              <Check className="h-3.5 w-3.5" />
                              {isAccepted ? "Accepted" : "Accept"}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-8 gap-1.5 text-slate-500"
                              aria-pressed={isRejected}
                              onClick={() => setStatus([suggestion.id], isRejected ? "pending" : "rejected")}
                            >
                              <X className="h-3.5 w-3.5" />
                              {isRejected ? "Undo reject" : "Reject"}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-8 gap-1.5"
                              onClick={() => setEditingId(isEditing ? null : suggestion.id)}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                              {isEditing ? "Done" : "Edit"}
                            </Button>
                            {suggestion.anchor.action !== "list" && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 gap-1.5 text-slate-500"
                                onClick={() =>
                                  setExpanded((prev) => ({ ...prev, [suggestion.id]: !prev[suggestion.id] }))
                                }
                              >
                                <Eye className="h-3.5 w-3.5" />
                                {expanded[suggestion.id] ? "Hide paragraph" : "Show paragraph"}
                              </Button>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </CardContent>
                )}
              </Card>
            );
          })}
        </section>

        {/* RIGHT — document text + manual placeholders */}
        <aside className="min-w-0 space-y-4 lg:sticky lg:top-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <MousePointerClick className="h-5 w-5 text-slate-500" />
                Manual placeholders
              </CardTitle>
              <CardDescription>
                Missed something? Select text below and convert it. Every occurrence is replaced.
              </CardDescription>
              {selectedText ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-700" title={selectedText}>
                    “{selectedText}”
                  </span>
                  <Button size="sm" className="h-8 gap-1.5" onClick={openConvertDialog}>
                    <Plus className="h-3.5 w-3.5" />
                    Convert
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0"
                    onClick={() => {
                      setSelectedText("");
                      window.getSelection()?.removeAllRanges();
                    }}
                  >
                    <X className="h-4 w-4" />
                    <span className="sr-only">Clear selection</span>
                  </Button>
                </div>
              ) : (
                selectionNotice && <p className="text-xs text-amber-700">{selectionNotice}</p>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {manual.length > 0 && (
                <ul className="space-y-2">
                  {manual.map((item) => (
                    <li key={item.id} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 text-sm">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-slate-600" title={item.sample_text}>“{item.sample_text}”</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <MonoKey name={item.placeholder_key} />
                          <Badge variant="outline">{fieldTypeLabel(item.field_type ?? "text")}</Badge>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 text-slate-400 hover:text-red-600"
                        onClick={() => {
                          setManual((prev) => prev.filter((r) => r.id !== item.id));
                          setPreview(null);
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                        <span className="sr-only">Remove</span>
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <div
                ref={documentRef}
                onMouseUp={handleSelection}
                onTouchEnd={handleSelection}
                onKeyUp={handleSelection}
                className="max-h-[55vh] space-y-4 overflow-y-auto rounded-lg border border-slate-100 p-2"
              >
                {content.segments.length === 0 && (
                  <p className="p-4 text-center text-sm text-slate-500">This document has no text.</p>
                )}
                {LOCATION_ORDER.filter((location) => segmentsByLocation[location]?.length).map((location) => (
                  <div key={location} className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {LOCATION_LABEL[location]}
                    </p>
                    {segmentsByLocation[location]!.map((segment) => (
                      <p
                        key={segment.index}
                        className="whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-xs leading-relaxed text-slate-700 hover:bg-slate-50"
                      >
                        <HighlightedText text={segment.text} />
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

      {/* Sticky apply bar */}
      <div className="sticky bottom-0 z-30 rounded-t-xl border bg-white/95 px-4 py-3 shadow-lg backdrop-blur">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 text-sm">
            <p className="font-medium text-slate-900">
              {changeCount} change{changeCount === 1 ? "" : "s"} ready
              {accepted.length > 0 && manual.length > 0
                ? ` (${accepted.length} suggested, ${manual.length} manual)`
                : ""}
            </p>
            {blockingProblem && changeCount > 0 && <p className="text-xs text-red-600">{blockingProblem}</p>}
            {!blockingProblem && typeConflicts.length > 0 && (
              <p className="text-xs text-amber-700">
                {typeConflicts.join(", ")} {typeConflicts.length === 1 ? "has" : "have"} different types —
                the first one wins.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" className="gap-2" disabled={!!blockingProblem || previewLoading} onClick={runPreview}>
              {previewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
              Preview
            </Button>
            <Button className="gap-2" disabled={!!blockingProblem || isApplying} onClick={() => setApplyOpen(true)}>
              {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eraser className="h-4 w-4" />}
              Apply cleaning
            </Button>
          </div>
        </div>
      </div>

      {/* Manual convert dialog */}
      <Dialog open={convertOpen} onOpenChange={setConvertOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Convert selection to placeholder</DialogTitle>
            <DialogDescription>
              Every occurrence of the selected text in the document becomes this placeholder.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Selected text</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-700">{selectedText}</p>
          </div>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(stageManual)} className="space-y-4">
              <FormField
                control={form.control}
                name="placeholder_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Placeholder key</FormLabel>
                    <FormControl>
                      <Input placeholder="meeting_title" className="font-mono" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="field_label"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Label (optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Meeting Title" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="field_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Field type</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="bg-white text-slate-900">
                          {FIELD_TYPE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="section"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Section (optional)</FormLabel>
                      <FormControl>
                        <Input placeholder="Meeting Details" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <DialogFooter className="gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setConvertOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit">Add placeholder</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Preview dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Preview of the cleaned template</DialogTitle>
            <DialogDescription>Nothing is saved yet. Placeholders are highlighted.</DialogDescription>
          </DialogHeader>
          {previewLoading && (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-5/6" />
              <Skeleton className="h-6 w-4/6" />
            </div>
          )}
          {previewError && <Notice tone="error">{previewError}</Notice>}
          {preview && !previewLoading && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                {preview.detected_keys.length} placeholder{preview.detected_keys.length === 1 ? "" : "s"}:{" "}
                {preview.detected_keys.map((key) => (
                  <MonoKey key={key} name={key} className="mr-1 mt-1" />
                ))}
              </p>
              {preview.warnings.render_error && (
                <Notice tone="error" title="This would not render">{preview.warnings.render_error}</Notice>
              )}
              {preview.results.some((r) => !r.matched) && (
                <Notice tone="warning" title="Some changes cannot be applied">
                  {preview.results
                    .filter((r) => !r.matched)
                    .map((r) => r.placeholder_key)
                    .join(", ")}
                </Notice>
              )}
              <div className="max-h-[50vh] space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-3">
                {preview.segments.map((segment) => (
                  <p key={segment.index} className="whitespace-pre-wrap break-words text-sm text-slate-700">
                    {segment.location !== "body" && (
                      <span className="mr-2 text-[10px] uppercase text-slate-400">{segment.location}</span>
                    )}
                    <HighlightedText text={segment.text} />
                  </p>
                ))}
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              Keep editing
            </Button>
            <Button
              disabled={!preview || previewLoading || !!blockingProblem}
              onClick={() => {
                setPreviewOpen(false);
                setApplyOpen(true);
              }}
            >
              Looks good — apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Apply confirm */}
      <Dialog open={applyOpen} onOpenChange={(open) => !isApplying && setApplyOpen(open)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Apply cleaning?</DialogTitle>
            <DialogDescription>
              {changeCount} change{changeCount === 1 ? "" : "s"} will be written to a processed copy. Your original
              file is preserved.
              {content.has_processed ? " The existing processed copy will be replaced." : ""}
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
            {accepted.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 max-w-[60%] truncate text-slate-600">
                  {s.sample_text ? `“${s.sample_text.split("\n")[0]}”` : "(empty spot)"}
                </span>
                <span className="text-slate-400">→</span>
                <MonoKey name={decisions[s.id].key} />
              </li>
            ))}
            {manual.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 max-w-[60%] truncate text-slate-600">“{m.sample_text}”</span>
                <span className="text-slate-400">→</span>
                <MonoKey name={m.placeholder_key} />
              </li>
            ))}
          </ul>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setApplyOpen(false)} disabled={isApplying}>
              Cancel
            </Button>
            <Button onClick={applyCleaning} disabled={isApplying} className="gap-2">
              {isApplying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Applying…
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  Confirm and apply
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
