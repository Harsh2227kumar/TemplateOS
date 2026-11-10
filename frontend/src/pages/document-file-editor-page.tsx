import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { toast } from "@/components/ui/toast";
import { DraftNotFound } from "@/features/documents/DraftLoadStates";
import { EditorPage } from "@/features/word-editor/EditorPage";
import { useDocument } from "@/hooks/queries";
import { parseRouteId } from "@/lib/route-params";

/** V1.7 P2.1: edit a generated version's Word file at /documents/:id/edit-file?version=n. */
export function DocumentFileEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const documentId = parseRouteId(id) ?? 0;
  const version = parseRouteId(searchParams.get("version") ?? undefined) ?? undefined;
  const document = useDocument(documentId).data ?? null;

  if (!documentId) {
    return <DraftNotFound title="Document not found" description="This link is not valid." backTo="/" backLabel="Go to Dashboard" />;
  }

  return (
    <EditorPage
      target={{ type: "document", id: documentId, version }}
      fileName={document?.name || `Draft ${documentId}`}
      backTo={`/documents/${documentId}/preview`}
      backLabel="Preview"
      onSaved={(session) => {
        toast({
          title: session.result_version ? `Version ${session.result_version} saved (edited manually)` : "Saved",
          description: "The form values were not changed.",
          duration: 4000,
        });
        navigate(`/documents/${documentId}/preview`);
      }}
    />
  );
}
