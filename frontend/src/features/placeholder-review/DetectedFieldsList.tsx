import { CheckCircle2, Copy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MonoKey } from "@/components/fields/pipeline-ui";
import type { PlaceholderDetectionResponse, TemplateField } from "@/lib/api";
import { fieldTypeLabel } from "@/lib/template-pipeline";

interface DetectedFieldsListProps {
  /** Fields in display order. */
  fields: TemplateField[];
  detection: PlaceholderDetectionResponse | null;
}

/** The valid placeholders, in document order, with new / repeated / stale markers. */
export function DetectedFieldsList({ fields, detection }: DetectedFieldsListProps) {
  const staleSet = new Set(detection?.stale_fields ?? []);
  const addedSet = new Set(detection?.added_fields ?? []);
  const duplicateCounts = new Map((detection?.warnings.duplicates ?? []).map((d) => [d.key, d.count]));

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          Valid placeholders ({fields.length})
        </CardTitle>
        <CardDescription>
          In document order. Repeated placeholders map to one field that fills every spot.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <ol className="divide-y divide-slate-100">
          {fields.map((field, index) => {
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
  );
}
