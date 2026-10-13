import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Braces,
  CheckCircle2,
  Copy,
  Eraser,
  Loader2,
  RefreshCw,
  ScanSearch,
  Wrench,
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { MonoKey, Notice, PipelineLoadError, PipelineSteps } from "@/components/fields/pipeline-ui";
import { templatesApi, type PlaceholderDetectionResponse, type TemplateField } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import { getAccessToken } from "@/lib/auth-token";
import {
  KEY_PATTERN,
  KEY_RULE_MESSAGE,
  canManageTemplate,
  fieldTypeLabel,
  pipelineErrorMessage,
  type ManagedTemplate,
} from "@/lib/template-pipeline";

export function PlaceholderReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const templateId = Number(id);

  const [template, setTemplate] = useState<ManagedTemplate | null>(null);
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [detection, setDetection] = useState<PlaceholderDetectionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ message: string; status?: number } | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [busy, setBusy] = useState<"detect" | "rebuild" | "fix" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [fixKeys, setFixKeys] = useState<Record<string, string>>({});
  const autoScanned = useRef(false);

  const canManage = canManageTemplate(template, user);

  useEffect(() => {
    let active = true;
    autoScanned.current = false;
    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      setDetection(null);
      try {
        const token = getAccessToken();
        const [templateData, fieldData] = await Promise.all([
          templatesApi.getTemplateDetail(token, templateId),
          templatesApi.getFields(token, templateId),
        ]);
        if (!active) return;
        setTemplate(templateData);
        setFields(fieldData);
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

  const applyDetection = (result: PlaceholderDetectionResponse) => {
    setDetection(result);
    setFields(result.detected_fields);
    setTemplate((prev) => (prev ? { ...prev, status: result.status || prev.status } : prev));
    setFixKeys(
      Object.fromEntries(result.warnings.invalid_names.map((w) => [w.raw, w.suggested_key])),
    );
  };

  const runDetection = useCallback(
    async (force: boolean, quiet = false) => {
      setBusy(force ? "rebuild" : "detect");
      setActionError(null);
      if (!quiet) setActionMessage(null);
      try {
        const result = await templatesApi.detectPlaceholders(getAccessToken(), templateId, force);
        applyDetection(result);
        if (!quiet) {
          const added = result.added_fields?.length ?? 0;
          const total = result.detected_fields.length;
          setActionMessage(
            total === 0
              ? "Scan complete — no placeholders found."
              : force
                ? `Fields rebuilt from the document — ${total} field${total === 1 ? "" : "s"}.`
                : added > 0
                  ? `Scan complete — ${added} new field${added === 1 ? "" : "s"} added.`
                  : "Scan complete — your fields are up to date.",
          );
        }
      } catch (err: any) {
        setActionError(pipelineErrorMessage(err, "detect placeholders"));
      } finally {
        setBusy(null);
        setRebuildOpen(false);
      }
    },
    [templateId],
  );

  // Refresh warnings automatically once fields exist (non-force only adds
  // new keys, never changes configured fields).
  useEffect(() => {
    if (!isLoading && template && canManage && fields.length > 0 && !detection && !autoScanned.current) {
      autoScanned.current = true;
      runDetection(false, true);
    }
  }, [isLoading, template, canManage, fields.length, detection, runDetection]);

  const fixInvalid = async (raws: string[]) => {
    const fixes = raws
      .map((raw) => ({ raw, key: (fixKeys[raw] ?? "").trim() }))
      .filter((fix) => KEY_PATTERN.test(fix.key));
    if (fixes.length === 0 || busy) return;
    setBusy("fix");
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await templatesApi.fixPlaceholders(getAccessToken(), templateId, fixes);
      applyDetection(result);
      setActionMessage(
        `Fixed ${fixes.length} placeholder name${fixes.length === 1 ? "" : "s"} in the cleaned copy.`,
      );
    } catch (err: any) {
      setActionError(pipelineErrorMessage(err, "fix placeholders"));
    } finally {
      setBusy(null);
    }
  };

  const sortedFields = useMemo(
    () => [...fields].sort((a, b) => a.display_order - b.display_order),
    [fields],
  );
  const staleSet = new Set(detection?.stale_fields ?? []);
  const addedSet = new Set(detection?.added_fields ?? []);
  const duplicateCounts = new Map((detection?.warnings.duplicates ?? []).map((d) => [d.key, d.count]));
  const fieldNames = new Set(fields.map((f) => f.field_name));

  if (isLoading) {
    return (
      <div className="max-w-4xl space-y-6">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-5 w-full max-w-sm" />
        <Skeleton className="h-72 w-full rounded-2xl" />
      </div>
    );
  }

  if (loadError || !template) {
    return (
      <PipelineLoadError
        status={loadError?.status}
        message={loadError?.message}
        onBack={() => navigate("/templates")}
        onRetry={() => setReloadToken((n) => n + 1)}
      />
    );
  }

  const invalid = detection?.warnings.invalid_names ?? [];
  const hasRunDetection = detection !== null || template.status !== "uploaded";
  const scanning = busy === "detect" || busy === "rebuild";
  const hasProcessed = Boolean(template.processed_file_path);

  return (
    <div className="max-w-4xl space-y-6 pb-10">
      <div className="space-y-3">
        <Button variant="ghost" onClick={() => navigate(`/templates/${template.id}`)} className="-ml-4 text-slate-600">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Template
        </Button>
        <PipelineSteps current={2} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold sm:text-3xl">Placeholder Review</h1>
            <p className="mt-2 text-sm text-slate-600">
              {template.name} · {fields.length} field{fields.length === 1 ? "" : "s"}
              {detection
                ? ` · scanned the ${detection.source_file === "processed" ? "cleaned copy" : "original file"}`
                : ""}
            </p>
          </div>
          {canManage && hasRunDetection && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="gap-2" disabled={!!busy} onClick={() => runDetection(false)}>
                <RefreshCw className={`h-4 w-4 ${busy === "detect" ? "animate-spin" : ""}`} />
                Scan again
              </Button>
              {fields.length > 0 && (
                <Button variant="ghost" className="text-slate-600" disabled={!!busy} onClick={() => setRebuildOpen(true)}>
                  Rebuild fields
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {actionError && <Notice tone="error">{actionError}</Notice>}
      {actionMessage && !actionError && <Notice tone="success">{actionMessage}</Notice>}
      {scanning && (
        <Notice tone="info">
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Scanning the document for placeholders…
          </span>
        </Notice>
      )}

      {detection?.warnings.parse_error && (
        <Notice tone="error" title="This template cannot be generated yet">
          Some placeholders have invalid names, so the document engine cannot read the template. Fix the
          names below.
        </Notice>
      )}

      {invalid.length > 0 && (
        <Card className="border-red-200">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <CardTitle className="flex items-center gap-2 text-base text-red-700">
                  <AlertTriangle className="h-5 w-5" />
                  Invalid placeholders ({invalid.length})
                </CardTitle>
                <CardDescription>
                  These were skipped. Fix renames them in the cleaned copy and adds the fields.
                </CardDescription>
              </div>
              {canManage && invalid.length > 1 && (
                <Button
                  size="sm"
                  className="gap-1.5"
                  disabled={!!busy || invalid.some((w) => !KEY_PATTERN.test(fixKeys[w.raw] ?? ""))}
                  onClick={() => fixInvalid(invalid.map((w) => w.raw))}
                >
                  <Wrench className="h-4 w-4" />
                  Fix all
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {invalid.map((warning) => {
              const key = fixKeys[warning.raw] ?? "";
              const valid = KEY_PATTERN.test(key);
              return (
                <div key={warning.raw} className="space-y-2 rounded-lg border border-red-100 bg-red-50/50 p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <code className="break-all rounded bg-white px-1.5 py-0.5 font-mono text-xs text-red-700">
                      {`{{${warning.raw}}}`}
                    </code>
                    <span className="text-xs text-slate-500">
                      {warning.count} occurrence{warning.count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {canManage ? (
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                      <div className="min-w-0 flex-1">
                        <Input
                          value={key}
                          aria-label={`New key for ${warning.raw}`}
                          aria-invalid={!valid}
                          className={`h-9 font-mono text-sm ${valid ? "" : "border-red-400"}`}
                          onChange={(e) => setFixKeys((prev) => ({ ...prev, [warning.raw]: e.target.value.trim() }))}
                        />
                        {!valid && <p className="mt-1 text-xs text-red-600">{KEY_RULE_MESSAGE}</p>}
                        {valid && fieldNames.has(key) && (
                          <p className="mt-1 text-xs text-slate-500">Uses the existing “{key}” field.</p>
                        )}
                      </div>
                      <Button
                        size="sm"
                        className="h-9 gap-1.5"
                        disabled={!valid || !!busy}
                        onClick={() => fixInvalid([warning.raw])}
                      >
                        {busy === "fix" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
                        Fix
                      </Button>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-600">
                      Suggested name: <MonoKey name={warning.suggested_key} />
                    </p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {sortedFields.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              Valid placeholders ({sortedFields.length})
            </CardTitle>
            <CardDescription>
              In document order. Repeated placeholders map to one field that fills every spot.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <ol className="divide-y divide-slate-100">
              {sortedFields.map((field, index) => {
                const stale = staleSet.has(field.field_name);
                const repeats = duplicateCounts.get(field.field_name);
                return (
                  <li key={field.id} className="flex items-start gap-3 px-4 py-3 sm:px-6">
                    <span className="mt-0.5 w-6 shrink-0 text-center font-mono text-xs text-slate-400">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="break-words font-medium text-slate-900">
                          {field.field_label || field.field_name}
                        </span>
                        <MonoKey name={field.field_name} />
                        {addedSet.has(field.field_name) && (
                          <Badge variant="outline" className="border-indigo-200 bg-indigo-50 text-indigo-700">
                            New
                          </Badge>
                        )}
                        {repeats && (
                          <Badge variant="outline" className="gap-1 border-slate-200 text-slate-600">
                            <Copy className="h-3 w-3" />
                            {repeats}×
                          </Badge>
                        )}
                        {stale && (
                          <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
                            Not in document
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                        {field.section && <span>Section: {field.section}</span>}
                        {field.is_required ? <span>Required</span> : <span>Optional</span>}
                        {field.validation_rule && <span>Rule: {field.validation_rule}</span>}
                        {field.example_value && (
                          <span className="min-w-0 truncate">Example: {field.example_value}</span>
                        )}
                      </div>
                    </div>
                    <Badge variant="outline" className="shrink-0 bg-slate-50">
                      {fieldTypeLabel(field.field_type)}
                    </Badge>
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>
      ) : hasRunDetection && !scanning ? (
        <EmptyState
          icon={Braces}
          title="No placeholders yet"
          description={
            hasProcessed
              ? "The cleaned copy has no valid {{placeholders}}. Clean the template again to add some."
              : "This document has no {{placeholders}}. Template Cleaning finds the blanks, labels and sample values for you."
          }
          actionLabel="Clean this template"
          onAction={canManage ? () => navigate(`/templates/${template.id}/clean`) : undefined}
        />
      ) : (
        !scanning && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ScanSearch className="h-5 w-5 text-slate-500" />
                Detect placeholders
              </CardTitle>
              <CardDescription>
                Scan the {hasProcessed ? "cleaned copy" : "document"} for{" "}
                <span className="font-mono text-xs">{"{{placeholder}}"}</span> tokens. Each valid one becomes a
                form field with a suggested label and type.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {canManage ? (
                <>
                  <Button className="gap-2" onClick={() => runDetection(false)} disabled={!!busy}>
                    <ScanSearch className="h-4 w-4" />
                    Detect placeholders
                  </Button>
                  {!hasProcessed && (
                    <Button variant="outline" className="gap-2" onClick={() => navigate(`/templates/${template.id}/clean`)}>
                      <Eraser className="h-4 w-4" />
                      Clean first
                    </Button>
                  )}
                </>
              ) : (
                <p className="text-sm text-slate-600">Only template managers can run placeholder detection.</p>
              )}
            </CardContent>
          </Card>
        )
      )}

      {detection && (detection.stale_fields?.length ?? 0) > 0 && (
        <Notice
          tone="warning"
          title="Fields without a placeholder"
          action={
            canManage ? (
              <Button size="sm" variant="outline" onClick={() => navigate(`/templates/${template.id}/fields`)}>
                Review in Field Setup
              </Button>
            ) : undefined
          }
        >
          {detection.stale_fields!.length} field{detection.stale_fields!.length === 1 ? " is" : "s are"} not used by the
          document. They will be ignored when generating — remove them if they are not needed.
        </Notice>
      )}

      <div className="flex flex-wrap gap-3 border-t pt-6">
        {fields.length > 0 && (
          <Button className="gap-2" onClick={() => navigate(`/templates/${template.id}/fields`)}>
            Continue to Field Setup
            <ArrowRight className="h-4 w-4" />
          </Button>
        )}
        {canManage && (
          <Button
            variant={fields.length > 0 ? "outline" : "default"}
            className="gap-2"
            onClick={() => navigate(`/templates/${template.id}/clean`)}
          >
            <Eraser className="h-4 w-4" />
            Clean template
          </Button>
        )}
      </div>

      <Dialog open={rebuildOpen} onOpenChange={(open) => !busy && setRebuildOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rebuild fields from the document?</DialogTitle>
            <DialogDescription>
              All {fields.length} field{fields.length === 1 ? "" : "s"} are recreated from the placeholders in the
              document, in document order. Labels, types and other settings you changed are reset (example values
              are kept). Use “Scan again” to only add new placeholders.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setRebuildOpen(false)} disabled={!!busy}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => runDetection(true)} disabled={!!busy}>
              {busy === "rebuild" ? "Rebuilding…" : "Rebuild fields"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
