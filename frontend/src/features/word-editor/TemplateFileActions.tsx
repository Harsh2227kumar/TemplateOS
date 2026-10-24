import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, FilePenLine, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { useCustomizeTemplate } from "@/hooks/queries/word-editor-actions";
import type { TemplateResponse } from "@/lib/api";

import { MANAGER_EDIT_WARNING, templateEditorActions } from "./word-editor-model";

/**
 * V1.7 P2.1 template detail buttons: "Edit Word file" (managers; a warning
 * first on a shared original) and "Customize for me" (a private copy).
 * Rendered only once the editor is known to be enabled.
 */
export function TemplateFileActions({ template }: { template: TemplateResponse }) {
  const navigate = useNavigate();
  const customize = useCustomizeTemplate();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const actions = templateEditorActions(template, true);
  const editFilePath = `/templates/${template.id}/edit-file`;

  const handleCustomize = async () => {
    if (customize.isPending) return;
    try {
      const copy = await customize.mutateAsync(template.id);
      toast({ title: `Created "${copy.name}"`, description: "Only you can see it. Edit its Word file now.", duration: 4000 });
      navigate(`/templates/${copy.id}/edit-file`);
    } catch (err) {
      toast({ variant: "destructive", title: "Couldn't create your copy", description: err instanceof Error ? err.message : undefined });
    }
  };

  return (
    <>
      {actions.editFile && (
        <Button
          variant="outline"
          className="gap-2"
          onClick={() => (actions.confirmEdit ? setConfirmOpen(true) : navigate(editFilePath))}
        >
          <FilePenLine className="h-4 w-4" />
          Edit Word file
        </Button>
      )}
      {actions.customize && (
        <Button
          variant="outline"
          className="gap-2"
          onClick={() => void handleCustomize()}
          disabled={customize.isPending}
        >
          {customize.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
          Customize for me
        </Button>
      )}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit the shared template?</DialogTitle>
            <DialogDescription>{MANAGER_EDIT_WARNING}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => navigate(editFilePath)}>Edit Word file</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
