import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { FieldFormValue } from "./field-setup-schema";

interface DeleteFieldDialogProps {
  /** The row being deleted; null closes the dialog. */
  field: Partial<FieldFormValue> | null;
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteFieldDialog({ field, open, onCancel, onConfirm }: DeleteFieldDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete field?</DialogTitle>
          <DialogDescription>
            {field && (
              <>
                “{field.field_label?.trim() || field.field_name || "New field"}” is removed now and deleted from the
                template when you save.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            <Trash2 className="mr-2 h-4 w-4" />
            Remove field
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
