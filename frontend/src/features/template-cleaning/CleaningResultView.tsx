import { ArrowLeft, ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MonoKey, Notice, PipelineSteps } from "@/components/fields/pipeline-ui";
import type { CleanResponse } from "@/lib/api";
import { fieldTypeLabel } from "@/lib/template-pipeline";

interface CleaningResultViewProps {
  templateName: string;
  result: CleanResponse;
  onBack: () => void;
  onReviewPlaceholders: () => void;
  onFieldSetup: () => void;
  onCleanAgain: () => void;
}

/** Shown after "Apply cleaning" succeeded. */
export function CleaningResultView({
  templateName,
  result,
  onBack,
  onReviewPlaceholders,
  onFieldSetup,
  onCleanAgain,
}: CleaningResultViewProps) {
  const created = result.created_fields.length;
  const stale = result.warnings.stale_fields ?? [];
  const detected = result.detected_keys?.length ?? 0;
  return (
    <div className="max-w-4xl space-y-6 pb-10">
      <Button variant="ghost" onClick={onBack} className="-ml-4 text-slate-600">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Template
      </Button>
      <PipelineSteps current={1} />
      <div>
        <h1 className="text-2xl font-semibold sm:text-3xl">Cleaning applied</h1>
        <p className="mt-2 text-sm text-slate-600">
          {templateName} · Status: <span className="font-medium capitalize">{result.status.replace(/_/g, " ")}</span>
        </p>
      </div>

      <Notice tone="success" title={`Processed template saved. ${created} new ${created === 1 ? "field" : "fields"}.`}>
        The original file is unchanged. The processed copy now has {detected} placeholder
        {detected === 1 ? "" : "s"} and is what documents will be generated from.
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
          {stale.map((key) => <MonoKey key={key} name={key} className="mr-1" />)} no longer appear in the
          document. Remove them in Field Setup if they are not needed.
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
        <Button className="gap-2" onClick={onReviewPlaceholders}>
          Review placeholders
          <ArrowRight className="h-4 w-4" />
        </Button>
        <Button variant="outline" onClick={onFieldSetup}>
          Field Setup
        </Button>
        <Button variant="ghost" onClick={onCleanAgain}>
          Clean again
        </Button>
      </div>
    </div>
  );
}
