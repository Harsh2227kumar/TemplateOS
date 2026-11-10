import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/context/auth-context";
import {
  combineQueries,
  useDetectPlaceholders,
  useFixPlaceholders,
  useTemplate,
  useTemplateFields,
} from "@/hooks/queries";
import type { ApiError, PlaceholderDetectionResponse } from "@/lib/api";
import { KEY_PATTERN, canManageTemplate, pipelineErrorMessage } from "@/lib/template-pipeline";

import type { DetectionBusy } from "./types";

/**
 * State and actions of the Placeholder Review page. Template and fields come
 * from the query cache; the detection mutations write the new field list and
 * status back into it. The latest detection report (warnings, added/stale
 * keys) is page-local, as before.
 */
export function usePlaceholderReview(templateId: number) {
  const { user } = useAuth();
  const templateQuery = useTemplate(templateId);
  const fieldsQuery = useTemplateFields(templateId);
  const load = combineQueries<ApiError>([templateQuery, fieldsQuery]);
  const detect = useDetectPlaceholders(templateId);
  const fix = useFixPlaceholders(templateId);

  const template = templateQuery.data ?? null;
  const fields = useMemo(() => fieldsQuery.data ?? [], [fieldsQuery.data]);

  // The latest detection report, tagged with its template so another template starts clean.
  const [report, setReport] = useState<{ templateId: number; result: PlaceholderDetectionResponse } | null>(null);
  const detection = report?.templateId === templateId ? report.result : null;
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [fixKeys, setFixKeys] = useState<Record<string, string>>({});
  // Template the automatic scan ran for. A ref, so StrictMode's second effect
  // pass in development does not scan twice.
  const autoScannedFor = useRef<number | null>(null);

  const canManage = canManageTemplate(template, user);
  const busy: DetectionBusy = detect.isPending
    ? detect.variables
      ? "rebuild"
      : "detect"
    : fix.isPending
      ? "fix"
      : null;

  const applyDetection = (result: PlaceholderDetectionResponse) => {
    setReport({ templateId, result });
    setFixKeys(Object.fromEntries(result.warnings.invalid_names.map((w) => [w.raw, w.suggested_key])));
  };

  const { mutateAsync: detectAsync } = detect;
  const runDetection = useCallback(
    async (force: boolean, quiet = false) => {
      setActionError(null);
      if (!quiet) setActionMessage(null);
      try {
        const result = await detectAsync(force);
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
        setRebuildOpen(false);
      }
    },
    // applyDetection only closes over templateId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [detectAsync, templateId],
  );

  // Refresh warnings automatically once fields exist (non-force only adds
  // new keys, never changes configured fields). Once per page visit.
  useEffect(() => {
    if (
      !load.isLoading &&
      template &&
      canManage &&
      fields.length > 0 &&
      !detection &&
      autoScannedFor.current !== templateId
    ) {
      autoScannedFor.current = templateId;
      void runDetection(false, true);
    }
  }, [load.isLoading, template, canManage, fields.length, detection, runDetection, templateId]);

  const fixInvalid = async (raws: string[]) => {
    const fixes = raws
      .map((raw) => ({ raw, key: (fixKeys[raw] ?? "").trim() }))
      .filter((item) => KEY_PATTERN.test(item.key));
    if (fixes.length === 0 || busy) return;
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await fix.mutateAsync(fixes);
      applyDetection(result);
      setActionMessage(`Fixed ${fixes.length} placeholder name${fixes.length === 1 ? "" : "s"} in the cleaned copy.`);
    } catch (err: any) {
      setActionError(pipelineErrorMessage(err, "fix placeholders"));
    }
  };

  const sortedFields = useMemo(
    () => [...fields].sort((a, b) => a.display_order - b.display_order),
    [fields],
  );

  return {
    load,
    template,
    fields,
    sortedFields,
    detection,
    canManage,
    busy,
    actionError,
    actionMessage,
    rebuildOpen,
    setRebuildOpen,
    fixKeys,
    setFixKey: (raw: string, key: string) => setFixKeys((prev) => ({ ...prev, [raw]: key })),
    runDetection,
    fixInvalid,
  };
}
