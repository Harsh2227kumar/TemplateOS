import type { FormEventHandler, ReactNode, RefObject } from "react";
import { FormProvider, type UseFormReturn } from "react-hook-form";
import { AlertCircle } from "lucide-react";

import { AiRewriteAllBar } from "@/components/fields/AiRewriteAllBar";
import { DocumentFormSections, FormProgress } from "@/components/forms/DocumentFormSections";
import type { AiFieldContext } from "@/components/forms/DynamicField";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import type { DocumentFormValues, TemplateField } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DraftFormShellProps {
  form: UseFormReturn<DocumentFormValues>;
  formRef: RefObject<HTMLFormElement>;
  onSubmit: FormEventHandler<HTMLFormElement>;
  fields: TemplateField[];
  aiContext: AiFieldContext;
  /** Disables every input (saving, or redirecting after a save). */
  disabled: boolean;
  /** Page header: back button, title, badges. */
  header: ReactNode;
  /** Extra banner above the error (e.g. "Draft saved"). */
  notice?: ReactNode;
  saveError: string | null;
  title: string;
  description: ReactNode;
  /** Sticky footer content (buttons, Ctrl+S hint). */
  footer: ReactNode;
  footerClassName?: string;
}

/**
 * Layout shared by Create and Edit draft: header, banners, and the form card
 * with progress, the grouped fields and a sticky action footer.
 */
export function DraftFormShell({
  form,
  formRef,
  onSubmit,
  fields,
  aiContext,
  disabled,
  header,
  notice,
  saveError,
  title,
  description,
  footer,
  footerClassName,
}: DraftFormShellProps) {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">{header}</div>

      {notice}

      {saveError && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
          <p className="break-words text-red-800">{saveError}</p>
        </div>
      )}

      <FormProvider {...form}>
        <form ref={formRef} onSubmit={onSubmit} noValidate className="space-y-6">
          <Card>
            <CardHeader className="space-y-3">
              <div>
                <CardTitle>{title}</CardTitle>
                <CardDescription className="mt-1.5">{description}</CardDescription>
              </div>
              <FormProgress fields={fields} />
              <AiRewriteAllBar
                fields={fields}
                templateId={aiContext.templateId}
                documentId={aiContext.documentId}
                disabled={disabled}
              />
            </CardHeader>
            <CardContent>
              <fieldset disabled={disabled} className="min-w-0">
                <DocumentFormSections fields={fields} aiContext={aiContext} disabled={disabled} />
              </fieldset>
            </CardContent>
            <CardFooter
              className={cn(
                "sticky bottom-0 z-10 flex flex-col-reverse gap-2 rounded-b-lg border-t bg-slate-50/95 py-3 backdrop-blur sm:flex-row sm:items-center sm:gap-3",
                footerClassName,
              )}
            >
              {footer}
            </CardFooter>
          </Card>
        </form>
      </FormProvider>
    </div>
  );
}
