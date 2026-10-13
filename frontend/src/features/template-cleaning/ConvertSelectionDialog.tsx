import { useLayoutEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FIELD_TYPE_OPTIONS, keyToLabel, suggestKey } from "@/lib/template-pipeline";

import { convertSchema, type ConvertValues } from "./cleaning-model";

interface ConvertSelectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedText: string;
  /** Returns an error message when the values cannot be staged, else stages them. */
  onSubmit: (values: ConvertValues) => string | null;
}

/** "Convert selection to placeholder" form for text selected in the document. */
export function ConvertSelectionDialog({ open, onOpenChange, selectedText, onSubmit }: ConvertSelectionDialogProps) {
  const form = useForm<ConvertValues>({
    resolver: zodResolver(convertSchema),
    defaultValues: { placeholder_key: "", field_label: "", field_type: "text", section: "" },
  });

  // Prefill from the selection each time the dialog opens (before paint).
  useLayoutEffect(() => {
    if (!open) return;
    const key = suggestKey(selectedText).slice(0, 60);
    form.reset({ placeholder_key: key, field_label: key ? keyToLabel(key) : "", field_type: "text", section: "" });
    // Only on open: typing in the dialog must not be overwritten.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const stage = (values: ConvertValues) => {
    const error = onSubmit(values);
    if (error) form.setError("placeholder_key", { message: error });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Convert selection to placeholder</DialogTitle>
          <DialogDescription>
            Every occurrence of the selected text in the document becomes this placeholder.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Selected text</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-700">{selectedText}</p>
        </div>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(stage)} className="space-y-4">
            <FormField
              control={form.control}
              name="placeholder_key"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Placeholder key</FormLabel>
                  <FormControl>
                    <Input placeholder="meeting_title" className="font-mono" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="field_label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Label (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Meeting Title" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="field_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Field type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent className="bg-white text-slate-900">
                        {FIELD_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="section"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Section (optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Meeting Details" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <DialogFooter className="gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit">Add placeholder</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
