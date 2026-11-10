import { ArrowLeft, ListTodo } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MonoKey, Notice } from "@/components/fields/pipeline-ui";
import type { TemplateField } from "@/lib/api";
import { fieldTypeLabel } from "@/lib/template-pipeline";

/** Read-only field list for a locked template. */
export function LockedFieldsView({ fields, onBack }: { fields: TemplateField[]; onBack: () => void }) {
  return (
    <div className="max-w-4xl space-y-6 pb-10">
      <Button variant="ghost" onClick={onBack} className="-ml-4 text-slate-600">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Template
      </Button>
      <h1 className="text-2xl font-semibold sm:text-3xl">Field Setup</h1>
      <Notice tone="warning">This template is locked. Field settings are read-only.</Notice>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListTodo className="h-5 w-5" />
            Fields
          </CardTitle>
          <CardDescription>{fields.length} field(s), in display order.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <ol className="divide-y divide-slate-100">
            {fields.map((field, index) => (
              <li key={field.id} className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-6">
                <span className="text-sm font-medium text-slate-400">{index + 1}.</span>
                <span className="text-sm font-medium text-slate-900">{field.field_label || field.field_name}</span>
                <MonoKey name={field.field_name} />
                <Badge variant="outline" className="bg-slate-50">{fieldTypeLabel(field.field_type)}</Badge>
                {field.is_required && (
                  <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">required</Badge>
                )}
                {field.ai_enabled && (
                  <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">AI</Badge>
                )}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
