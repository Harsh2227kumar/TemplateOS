import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Loader2 } from "lucide-react";

import { AvatarFallback } from "@/components/ui/avatar-fallback";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/auth-context";
import { useUpdateProfile } from "@/hooks/queries";
import { ApiError, type User } from "@/lib/api";
import { formatRole } from "@/lib/format";

const profileSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(2, "Full name must contain at least 2 characters")
    .max(255, "Must be 255 characters or fewer"),
  phone: z.string().trim().max(50, "Must be 50 characters or fewer"),
  job_title: z.string().trim().max(255, "Must be 255 characters or fewer"),
});

type ProfileValues = z.infer<typeof profileSchema>;

function toValues(user: User | null): ProfileValues {
  return {
    full_name: user?.full_name ?? "",
    phone: user?.phone ?? "",
    job_title: user?.job_title ?? "",
  };
}

/** Who to ask about membership changes, by role. */
function membershipHint(role: string | undefined): string {
  if (role === "super_admin") return "Change these on the Admin → Users page.";
  if (role === "org_admin") return "Ask a super admin to change this.";
  if (role === "department_admin") return "Ask your organization admin to change this.";
  return "Ask your department admin to change this.";
}

function ProfileForm({ user }: { user: User }) {
  const updateProfile = useUpdateProfile();
  const [saved, setSaved] = useState(false);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toValues(user),
  });
  const { isSubmitting, isDirty, errors } = form.formState;

  useEffect(() => {
    form.reset(toValues(user));
  }, [user, form]);

  const submit = async (values: ProfileValues) => {
    setSaved(false);
    try {
      await updateProfile.mutateAsync({
        full_name: values.full_name,
        phone: values.phone || null,
        job_title: values.job_title || null,
      });
      setSaved(true);
    } catch (caught) {
      form.setError("root", {
        message: caught instanceof ApiError ? caught.message : "Could not save. Please try again.",
      });
    }
  };

  return (
    <Form {...form}>
      <form
        className="space-y-4 px-4 py-5 sm:px-6"
        onSubmit={form.handleSubmit(submit)}
        onChange={() => setSaved(false)}
        noValidate
      >
        <FormField
          control={form.control}
          name="full_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Full name</FormLabel>
              <FormControl>
                <Input autoComplete="name" maxLength={255} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="job_title"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Job title</FormLabel>
                <FormControl>
                  <Input autoComplete="organization-title" maxLength={255} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="phone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Phone number</FormLabel>
                <FormControl>
                  <Input type="tel" autoComplete="tel" maxLength={50} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        {errors.root?.message && (
          <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errors.root.message}</p>
        )}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting || !isDirty}>
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Save changes
          </Button>
          {saved && !isDirty && (
            <span className="text-sm text-emerald-700" role="status">
              Saved
            </span>
          )}
        </div>
      </form>
    </Form>
  );
}

export function ProfilePage() {
  const { user, isLoading } = useAuth();

  if (isLoading || !user) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="h-8 w-32 animate-pulse rounded-md bg-slate-200" />
        <div className="mt-8 h-96 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  const renderField = (label: string, value: React.ReactNode) => (
    <div className="py-4 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6 sm:py-5">
      <dt className="text-sm font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900 sm:col-span-2 sm:mt-0">
        {value ?? <span className="text-slate-400">—</span>}
      </dd>
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8 flex items-center gap-6">
        <AvatarFallback name={user.full_name} className="h-20 w-20 text-2xl" />
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold text-slate-900">{user.full_name}</h1>
          <p className="mt-1 text-sm text-slate-500">{formatRole(user.role)}</p>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-5 sm:px-6">
          <h3 className="text-base font-semibold leading-6 text-slate-900">Personal Information</h3>
          <p className="mt-1 text-sm text-slate-500">You can update these details yourself.</p>
        </div>
        <ProfileForm user={user} />
      </div>

      <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-5 sm:px-6">
          <h3 className="text-base font-semibold leading-6 text-slate-900">Account and membership</h3>
          <p className="mt-1 text-sm text-slate-500">
            Your role, organization and department decide which templates you can see and
            publish. {membershipHint(user.role)}
          </p>
        </div>
        <div className="px-4 py-5 sm:p-0">
          <dl className="sm:divide-y sm:divide-slate-200">
            {renderField("Email address", user.email)}
            {renderField(
              "Role",
              <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                {formatRole(user.role)}
              </span>,
            )}
            {renderField("Organization", user.organization)}
            {renderField("Department", user.department)}
            {renderField("Signature status", user.signature_path ? "Configured" : "Not configured")}
          </dl>
        </div>
      </div>

      {user.preferences && (
        <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50 px-4 py-5 sm:px-6">
            <h3 className="text-base font-semibold leading-6 text-slate-900">Preferences</h3>
            <p className="mt-1 text-sm text-slate-500">Application and notification settings.</p>
          </div>
          <div className="px-4 py-5 sm:p-0">
            <dl className="sm:divide-y sm:divide-slate-200">
              {renderField("Default document format", user.preferences.default_document_format?.toUpperCase())}
              {renderField("Email notifications", user.preferences.email_notifications ? "Enabled" : "Disabled")}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
