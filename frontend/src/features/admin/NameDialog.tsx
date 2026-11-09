import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
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
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";

const nameSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "A name is required")
    .max(255, "Must be 255 characters or fewer"),
  code: z
    .string()
    .trim()
    .max(32, "Must be 32 characters or fewer")
    .regex(/^[A-Za-z0-9-]*$/, "Use letters, digits and '-' only"),
});

type NameValues = z.infer<typeof nameSchema>;

interface NameDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  label: string;
  initialName?: string;
  submitLabel: string;
  /** Show a short code field (e.g. SIU / SIT / CSE, shared with EkLink). */
  withCode?: boolean;
  initialCode?: string | null;
  onSubmit: (name: string, code: string | null) => Promise<unknown>;
}

/** Create / rename an organization, institute or department (with an optional code). */
export function NameDialog({
  open,
  onOpenChange,
  title,
  description,
  label,
  initialName = "",
  submitLabel,
  withCode = false,
  initialCode = null,
  onSubmit,
}: NameDialogProps) {
  const form = useForm<NameValues>({
    resolver: zodResolver(nameSchema),
    defaultValues: { name: initialName, code: initialCode ?? "" },
  });
  const { isSubmitting, errors } = form.formState;

  useEffect(() => {
    if (open) form.reset({ name: initialName, code: initialCode ?? "" });
  }, [open, initialName, initialCode, form]);

  const submit = async (values: NameValues) => {
    try {
      const code = values.code.trim().toUpperCase();
      await onSubmit(values.name.replace(/\s+/g, " "), code || null);
      onOpenChange(false);
    } catch (caught) {
      form.setError("root", {
        message: caught instanceof ApiError ? caught.message : "Could not save. Please try again.",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !isSubmitting && onOpenChange(next)}>
      <DialogContent className="w-[calc(100%-2rem)] sm:w-full">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(submit)} noValidate>
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{label}</FormLabel>
                  <FormControl>
                    <Input autoFocus maxLength={255} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {withCode && (
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code (optional)</FormLabel>
                    <FormControl>
                      <Input maxLength={32} placeholder="e.g. SIT" className="uppercase" {...field} />
                    </FormControl>
                    <p className="text-xs text-slate-500">
                      Short code that EkLink uses to place users here on sign-in.
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {errors.root?.message && (
              <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errors.root.message}</p>
            )}
            <DialogFooter className="gap-2 sm:gap-0">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {submitLabel}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
