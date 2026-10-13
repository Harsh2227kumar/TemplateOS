import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { Badge } from "@/components/ui/badge";

import {
  ApiError,
  type TemplateAccessOptions,
  type TemplateResponse,
} from "@/lib/api";
import { UploadZone } from "./UploadZone";
import { useUploadTemplate } from "@/hooks/queries";
import { useAuth } from "@/context/auth-context";
import {
  AudienceFields,
  EMPTY_AUDIENCE,
  describeRoles,
  toAccessPayload,
  useAccessOptions,
  validateAudience,
  type AudienceErrors,
  type AudienceValue,
} from "@/components/templates/AudienceFields";


const CATEGORY_OPTIONS = [
  { label: "Notice", value: "notice" },
  { label: "Minutes of Meeting", value: "mom" },
  { label: "Report", value: "report" },
  { label: "Application", value: "application" },
  { label: "Letter", value: "letter" },
  { label: "Certificate", value: "certificate" },
  { label: "Proposal", value: "proposal" },
  { label: "Invoice", value: "invoice" },
  { label: "Custom", value: "custom" },
] as const;

const audienceSchema = z.object({
  visibility: z.union([
    z.enum(["private", "public", "organization", "department", "group"]),
    z.literal(""),
  ]),
  scope_organization: z.string(),
  scope_department: z.string(),
  role_mode: z.enum(["all", "selected"]),
  allowed_roles: z.array(z.string()),
});

interface AudienceContext {
  options: TemplateAccessOptions | null;
  role: string | undefined;
}

/**
 * The audience rules depend on data loaded at runtime (access options, the
 * user's role), so the schema reads them from a ref at validation time.
 */
function buildUploadSchema(context: { current: AudienceContext }) {
  return z.object({
    name: z.string().trim().min(1, "Template name is required").max(100, "Template name must be 100 characters or fewer"),
    description: z.string().max(500, "Description must be 500 characters or fewer").optional(),
    category: z.enum([
      "notice", "mom", "report", "application", "letter", "certificate", "proposal", "invoice", "custom"
    ], { required_error: "Please select a category", invalid_type_error: "Please select a category" }),
    audience: audienceSchema.superRefine((audience, ctx) => {
      const errors = validateAudience(audience, context.current.options, context.current.role);
      for (const [key, message] of Object.entries(errors)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: [key], message });
      }
    }),
    file: z.instanceof(File, { message: "Please select a .docx file to upload" }),
  });
}

type UploadTemplateValues = z.infer<ReturnType<typeof buildUploadSchema>>;

const DEFAULT_VALUES: Partial<UploadTemplateValues> = {
  name: "",
  description: "",
  category: undefined,
  audience: EMPTY_AUDIENCE,
  file: undefined,
};

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mapApiError(err: ApiError): string {
  const msg = err.message;
  if (err.status === 400 && msg.includes("DOCX"))
    return "Only .docx files are accepted. Please check your file.";
  if (err.status === 400 && (msg.includes("10 MB") || msg.toLowerCase().includes("size")))
    return "Your file is too large. Maximum size is 10 MB.";
  if (err.status === 401)
    return "Your session has expired. Please log in again.";
  if (err.status === 500)
    return "The server could not save your file. Please try again.";
  return msg;
}

interface UploadTemplateFormProps {
  onUploadStart?: () => void;
  onUploadSuccess?: () => void;
  /** Called when an upload attempt fails, or the form is reset for another upload. */
  onUploadReset?: () => void;
}

export function UploadTemplateForm({ onUploadStart, onUploadSuccess, onUploadReset }: UploadTemplateFormProps) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const uploadTemplate = useUploadTemplate();
  const { options: accessOptions, error: accessOptionsError } = useAccessOptions();

  const [error, setError] = useState("");
  const [success, setSuccess] = useState<TemplateResponse | null>(null);

  const audienceContext = useRef<AudienceContext>({ options: null, role: undefined });
  audienceContext.current = { options: accessOptions, role: user?.role };
  const schema = useMemo(() => buildUploadSchema(audienceContext), []);

  const form = useForm<UploadTemplateValues>({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: DEFAULT_VALUES,
  });

  const { isSubmitting } = form.formState;

  const resetForm = () => {
    form.reset(DEFAULT_VALUES);
    setError("");
    setSuccess(null);
    onUploadReset?.();
  };

  const onSubmit = async (values: UploadTemplateValues) => {
    setError("");

    try {
      onUploadStart?.();
      const access = toAccessPayload(values.audience);
      const result = await uploadTemplate.mutateAsync({
        file: values.file,
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        category: values.category,
        visibility: access.visibility,
        scope_organization: access.scope_organization ?? undefined,
        scope_department: access.scope_department ?? undefined,
        allowed_roles: access.allowed_roles ?? undefined,
      });
      setSuccess(result);
      onUploadSuccess?.();
    } catch (caught) {
      onUploadReset?.();
      setError(
        caught instanceof ApiError ? mapApiError(caught) : "Upload failed. Please try again.",
      );
    }
  };

  // ── Success view ──────────────────────────────────────────────────────────
  if (success) {
    return (
      <div className="space-y-4">
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
          ✓ &ldquo;{success.name}&rdquo; uploaded successfully.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="capitalize">{success.category}</Badge>
          <Badge variant="outline" className="capitalize">{success.visibility}</Badge>
          {success.scope_organization && (
            <Badge variant="outline">{success.scope_organization}</Badge>
          )}
          {success.scope_department && (
            <Badge variant="outline">{success.scope_department}</Badge>
          )}
          {success.allowed_roles?.length ? (
            <Badge variant="outline">Only: {describeRoles(success.allowed_roles, accessOptions)}</Badge>
          ) : null}
          <span className="text-sm text-slate-500">{formatBytes(success.file_size_bytes ?? 0)}</span>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="default"
            onClick={() => navigate(`/templates/${success.id}`)}
          >
            View Template
          </Button>
          <Button type="button" variant="outline" onClick={resetForm}>
            Upload Another
          </Button>
        </div>
      </div>
    );
  }

  // ── Form view ─────────────────────────────────────────────────────────────
  return (
    <Form {...form}>
      <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)} noValidate>
        {/* Template Name */}
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Template Name <span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <Input placeholder="e.g. Q3 Project Proposal" maxLength={100} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Description */}
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Description <span className="font-normal text-slate-500">(optional)</span>
              </FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Briefly describe this template…"
                  className="resize-none"
                  rows={3}
                  maxLength={500}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Category */}
        <FormField
          control={form.control}
          name="category"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Category <span className="text-red-500">*</span>
              </FormLabel>
              {/* Controlled (value, not defaultValue) so "Upload Another" resets the
                  trigger; closing the menu counts as blur for onBlur validation. */}
              <Select
                value={field.value ?? ""}
                onValueChange={(next) => {
                  field.onChange(next);
                  void form.trigger("category");
                }}
                onOpenChange={(open) => {
                  if (!open) field.onBlur();
                }}
              >
                <FormControl>
                  <SelectTrigger ref={field.ref}>
                    <SelectValue placeholder="Select a category" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {CATEGORY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Audience: visibility, scope and roles */}
        <FormField
          control={form.control}
          name="audience"
          render={({ field }) => {
            const audienceErrors = form.formState.errors.audience;
            const errors: AudienceErrors = {
              visibility: audienceErrors?.visibility?.message,
              scope_organization: audienceErrors?.scope_organization?.message,
              scope_department: audienceErrors?.scope_department?.message,
              allowed_roles: audienceErrors?.allowed_roles?.message,
            };
            return (
              <FormItem className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-slate-900">Audience</p>
                  <p className="text-xs text-slate-500">
                    Who can find and use this template.
                    {accessOptionsError &&
                      " Audience options could not be loaded, so only basic visibilities are available."}
                  </p>
                </div>
                <AudienceFields
                  value={field.value}
                  onChange={(next) => {
                    field.onChange(next);
                    if (form.formState.isSubmitted) void form.trigger("audience");
                  }}
                  options={accessOptions}
                  role={user?.role}
                  errors={errors}
                  disabled={isSubmitting}
                />
              </FormItem>
            );
          }}
        />

        {/* File Upload */}
        <FormField
          control={form.control}
          name="file"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                DOCX File <span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <UploadZone
                  file={field.value}
                  onChange={field.onChange}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Error banner */}
        {error && (
          <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>
        )}

        {/* Submit */}
        <Button className="w-full" type="submit" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Uploading…
            </>
          ) : (
            "Upload Template"
          )}
        </Button>
      </form>
    </Form>
  );
}
