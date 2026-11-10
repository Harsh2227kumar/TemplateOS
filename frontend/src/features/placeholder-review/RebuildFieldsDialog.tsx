import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { DetectionBusy } from "./types";

interface RebuildFieldsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fieldCount: number;
  busy: DetectionBusy;
  onConfirm: () => void;
}

export function RebuildFieldsDialog({ open, onOpenChange, fieldCount, busy, onConfirm }: RebuildFieldsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rebuild fields from the document?</DialogTitle>
          <DialogDescription>
            All {fieldCount} field{fieldCount === 1 ? "" : "s"} are recreated from the placeholders in the
            document, in document order. Labels, types and other settings you changed are reset (example values
            are kept). Use “Scan again” to only add new placeholders.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={!!busy}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={!!busy}>
            {busy === "rebuild" ? "Rebuilding…" : "Rebuild fields"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
