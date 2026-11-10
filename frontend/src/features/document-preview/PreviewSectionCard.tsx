import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PreviewSection } from "@/lib/api";

import { PreviewFieldRow } from "./PreviewFieldRow";

interface PreviewSectionCardProps {
  section: PreviewSection;
}

/** A form section rendered read-only as a definition list. */
export function PreviewSectionCard({ section }: PreviewSectionCardProps) {
  const fields = [...section.fields].sort((a, b) => a.display_order - b.display_order);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="break-words text-base">{section.name || "General"}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {fields.length === 0 ? (
          <p className="text-sm italic text-slate-400">No fields in this section.</p>
        ) : (
          <dl className="divide-y divide-slate-100">
            {fields.map((field) => (
              <PreviewFieldRow key={field.field_name} field={field} />
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
