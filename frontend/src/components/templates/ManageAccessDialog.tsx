import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUpdateTemplateAccess } from "@/hooks/queries";
import { ApiError, type TemplateResponse } from "@/lib/api";
import {
  AudienceFields,
  audienceFromTemplate,
  toAccessPayload,
  useAccessOptions,
  validateAudience,
  type AudienceErrors,
  type AudienceValue,
} from "./AudienceFields";

interface ManageAccessDialogProps {
  template: TemplateResponse;
  role: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The template cache is updated by the mutation; this is only a notification. */
  onSaved?: (template: TemplateResponse) => void;
}

export function ManageAccessDialog({
  template,
  role,
  open,
  onOpenChange,
  onSaved,
}: ManageAccessDialogProps) {
  const { options, error: optionsError } = useAccessOptions(open);
  const [value, setValue] = useState<AudienceValue>(() => audienceFromTemplate(template));
  const [errors, setErrors] = useState<AudienceErrors>({});
  const [submitted, setSubmitted] = useState(false);
  const updateAccess = useUpdateTemplateAccess();
  const saving = updateAccess.isPending;
  const [saveError, setSaveError] = useState<string | null>(null);

  // Start from the template's current audience every time the dialog opens.
  // Only on open: a refetched template must not overwrite edits in progress.
  const templateRef = useRef(template);
  templateRef.current = template;
  useEffect(() => {
    if (open) {
      setValue(audienceFromTemplate(templateRef.current));
      setErrors({});
      setSubmitted(false);
      setSaveError(null);
    }
  }, [open]);

  const handleChange = (next: AudienceValue) => {
    setValue(next);
    if (submitted) setErrors(validateAudience(next, options, role));
  };

  const handleSave = async () => {
    setSubmitted(true);
    const found = validateAudience(value, options, role);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    if (saving) return;
    setSaveError(null);
    try {
      const updated = await updateAccess.mutateAsync({ id: template.id, body: toAccessPayload(value) });
      onSaved?.(updated);
      onOpenChange(false);
    } catch (caught) {
      setSaveError(
        caught instanceof ApiError ? caught.message : "Could not update access. Please try again.",
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] overflow-y-auto sm:w-full">
        <DialogHeader>
          <DialogTitle>Manage access</DialogTitle>
          <DialogDescription>
            Choose where <span className="font-medium text-slate-900">{template.name}</span> is
            published and which roles can use it.
          </DialogDescription>
        </DialogHeader>

        {!options && !optionsError ? (
          <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading audience options…
          </div>
        ) : (
          <AudienceFields
            value={value}
            onChange={handleChange}
            options={options}
            role={role}
            errors={errors}
            disabled={saving}
          />
        )}

        {optionsError && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
            Audience options could not be loaded ({optionsError}). Only basic visibilities are
            available.
          </p>
        )}
        {saveError && (
          <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{saveError}</p>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving…
              </>
            ) : (
              "Save access"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
