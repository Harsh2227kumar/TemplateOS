import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";
import { ArrowLeft, ListTodo } from "lucide-react";

export function FieldSetupPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  return (
    <div className="max-w-4xl space-y-8 pb-10">
      <Button
        variant="ghost"
        onClick={() => navigate(`/templates/${id}/placeholders`)}
        className="-ml-4 text-slate-600"
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Placeholders
      </Button>
      <EmptyState
        icon={ListTodo}
        title="Field Setup is coming in Phase 3"
        description="Editing field labels, types, required flags, sections, and display order will happen here. For now, review the detected placeholders and come back once field setup is available."
        actionLabel="Field Setup"
      />
    </div>
  );
}
