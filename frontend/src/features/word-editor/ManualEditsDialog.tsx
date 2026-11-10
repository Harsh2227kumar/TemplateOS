import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import type { ManualEditsConflict } from "./word-editor-model";

interface ManualEditsDialogProps {
  conflict: ManualEditsConflict | null;
  generating: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** V1.7 P2.1: generate answered 409 "manual_edits": ask before replacing the hand-edited version. */
export function ManualEditsDialog({ conflict, generating, onCancel, onConfirm }: ManualEditsDialogProps) {
  return (
    <Dialog open={conflict !== null} onOpenChange={(open) => !open && !generating && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate over your manual edits?</DialogTitle>
          <DialogDescription>{conflict?.message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={generating}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm} disabled={generating}>
            {generating && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            Generate anyway
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
