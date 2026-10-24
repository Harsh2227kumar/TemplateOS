import { useNavigate, useParams } from "react-router-dom";

import { toast } from "@/components/ui/toast";
import { DraftNotFound } from "@/features/documents/DraftLoadStates";
import { EditorPage } from "@/features/word-editor/EditorPage";
import { TemplateEditorHelp } from "@/features/word-editor/TemplateEditorHelp";
import { useTemplate, useTemplateFields } from "@/hooks/queries";
import { parseRouteId } from "@/lib/route-params";

/** V1.7 P2.1: edit a template's Word file at /templates/:id/edit-file (managers / personal copies). */
export function TemplateFileEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const templateId = parseRouteId(id) ?? 0;
  const template = useTemplate(templateId).data ?? null;
  const fields = useTemplateFields(templateId).data ?? [];

  if (!templateId) {
    return <DraftNotFound title="Template not found" description="This link is not valid." backTo="/templates" backLabel="Back to Library" />;
  }

  return (
    <EditorPage
      target={{ type: "template", id: templateId }}
      fileName={template?.name ?? "Template"}
      backTo={`/templates/${templateId}`}
      backLabel="Template"
      help={<TemplateEditorHelp fields={fields} />}
      onSaved={(session) => {
        toast({ title: session.result_revision ? `Revision ${session.result_revision} saved` : "Template saved", duration: 2500 });
        navigate(`/templates/${templateId}/field-changes`);
      }}
    />
  );
}
