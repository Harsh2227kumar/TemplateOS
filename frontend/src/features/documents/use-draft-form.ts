import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { focusFirstError } from "@/components/forms/DocumentFormSections";
import { toast } from "@/components/ui/toast";
import { ApiError, splitValidationErrors, type DocumentFormValues, type TemplateField } from "@/lib/api";
import { buildFormSchema } from "@/lib/validation";

/**
 * The react-hook-form setup shared by Create and Edit draft: a schema built
 * from the template fields, the "n fields need attention" toast on invalid
 * submit, and mapping of a failed save (422 detail) onto the inputs.
 *
 * `fields` is a snapshot taken when the form was seeded, so a background
 * refetch of the fields query cannot change the schema under the user.
 */
export function useDraftForm(fields: TemplateField[]) {
  const schema = useMemo(() => buildFormSchema(fields), [fields]);
  const form = useForm<DocumentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {},
    mode: "onTouched",
    shouldFocusError: false,
  });
  const formRef = useRef<HTMLFormElement>(null);

  const handleInvalid = (errors: FieldErrors<DocumentFormValues>) => {
    const count = Object.keys(errors).length;
    focusFirstError(fields, errors);
    toast({
      variant: "destructive",
      title: count === 1 ? "1 field needs attention" : `${count} fields need attention`,
      description: "Fix the highlighted fields, then save again.",
      duration: 4000,
    });
  };

  /**
   * Show a failed save: field-specific 422 errors go inline; returns the
   * banner message, or null when every error was shown on a field.
   */
  const describeSaveError = (err: unknown, fallback: string): string | null => {
    const split =
      err instanceof ApiError && err.status === 422
        ? splitValidationErrors(err.detail, fields.map((f) => f.field_name))
        : null;
    if (!split) return err instanceof Error && err.message ? err.message : fallback;

    Object.entries(split.fieldErrors).forEach(([fieldName, message]) => {
      form.setError(fieldName, { message, type: "server" });
    });
    focusFirstError(fields, form.formState.errors);
    if (split.otherMessages.length > 0) return `Validation failed: ${split.otherMessages.join("; ")}`;
    if (Object.keys(split.fieldErrors).length === 0) {
      return (err as Error).message || "Validation failed. Please check the form.";
    }
    return null;
  };

  /** Submit the form programmatically (Ctrl+S). */
  const requestSubmit = () => formRef.current?.requestSubmit();

  return { form, formRef, handleInvalid, describeSaveError, requestSubmit };
}

/** Re-renders every 30s so relative times ("2 minutes ago") stay current. */
export function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
