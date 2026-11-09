import { useEffect, useMemo } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUpdateAdminUser } from "@/hooks/queries";
import {
  MEMBER_TYPES,
  buildUserUpdate,
  canChangeActive,
  canChangeDepartment,
  canChangeInstitute,
  canChangeMemberType,
  canChangeOrganization,
  canChangePlacement,
  canChangeRole,
  departmentsOf,
  eklinkUserUrl,
  isEklinkManaged,
  institutesOf,
  roleChoices,
  validateUserEdit,
  type Member,
} from "@/lib/admin-permissions";
import {
  ApiError,
  type AdminUser,
  type Department,
  type Institute,
  type Organization,
} from "@/lib/api";
import { formatRole } from "@/lib/format";
import { ManagedInEklink } from "@/features/admin/ManagedInEklink";

const NONE = "none";

const editSchema = z.object({
  role: z.string().min(1),
  organization_id: z.number().int().nullable(),
  institute_id: z.number().int().nullable(),
  department_id: z.number().int().nullable(),
  member_type: z.string().nullable(),
  is_active: z.boolean(),
});

type EditValues = z.infer<typeof editSchema>;

interface EditUserDialogProps {
  actor: Member;
  target: AdminUser | null;
  organizations: Organization[];
  institutes: Institute[];
  departments: Department[];
  /** EkLink base URL (from /admin/sync/status) for the "Open in EkLink" links. */
  eklinkUrl?: string | null;
  onOpenChange: (open: boolean) => void;
}

function IdSelect({
  value,
  onChange,
  disabled,
  noneLabel,
  choices,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  noneLabel: string;
  choices: { id: number; name: string }[];
}) {
  return (
    <Select
      value={value === null ? NONE : String(value)}
      onValueChange={(next) => onChange(next === NONE ? null : Number(next))}
      disabled={disabled}
    >
      <FormControl>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        <SelectItem value={NONE}>{noneLabel}</SelectItem>
        {choices.map((choice) => (
          <SelectItem key={choice.id} value={String(choice.id)}>
            {choice.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function EditUserDialog({
  actor,
  target,
  organizations,
  institutes,
  departments,
  eklinkUrl,
  onOpenChange,
}: EditUserDialogProps) {
  const open = target !== null;
  const updateUser = useUpdateAdminUser();
  const departmentOrg = useMemo(
    () => new Map(departments.map((department) => [department.id, department.organization_id])),
    [departments],
  );
  const departmentInstitute = useMemo(
    () => new Map(departments.map((department) => [department.id, department.institute_id ?? null])),
    [departments],
  );
  const schema = useMemo(
    () =>
      editSchema.superRefine((values, ctx) => {
        const problems = validateUserEdit(values, departmentOrg, departmentInstitute);
        for (const [path, message] of Object.entries(problems)) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
        }
      }),
    [departmentOrg, departmentInstitute],
  );

  const form = useForm<EditValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      role: "",
      organization_id: null,
      institute_id: null,
      department_id: null,
      member_type: null,
      is_active: true,
    },
  });
  const { isSubmitting, errors } = form.formState;

  useEffect(() => {
    if (target) {
      form.reset({
        role: target.role,
        organization_id: target.organization_id,
        institute_id: target.institute_id ?? null,
        department_id: target.department_id,
        member_type: target.member_type ?? null,
        is_active: target.is_active ?? true,
      });
    }
  }, [target, form]);

  if (!target) return null;

  // EkLink-linked users: placement, member type and the active flag come from EkLink.
  const managed = isEklinkManaged(target);
  const placementEditable = canChangePlacement(target);
  const eklinkLink = eklinkUserUrl(eklinkUrl, target.login_id);
  const roleEditable = canChangeRole(actor, target);
  const orgEditable = placementEditable && canChangeOrganization(actor);
  const instEditable = placementEditable && canChangeInstitute(actor);
  const deptEditable = placementEditable && canChangeDepartment(actor);
  const activeEditable = canChangeActive(actor, target);
  const memberTypeEditable = canChangeMemberType(actor, target);
  const roles = roleChoices(actor, target);
  const selectedOrg = form.watch("organization_id");
  const selectedInst = form.watch("institute_id");
  const selectedRole = form.watch("role");
  const instChoices = institutesOf(institutes, selectedOrg);
  // An institute admin only ever sees their own institute's departments.
  const deptChoices = departmentsOf(
    departments,
    selectedOrg,
    actor.role === "institute_admin" ? actor.institute_id ?? null : selectedInst,
  );
  const memberRole = (MEMBER_TYPES as readonly string[]).includes(selectedRole);

  const submit = async (values: EditValues) => {
    const body = buildUserUpdate(actor, target, values);
    if (Object.keys(body).length === 0) {
      onOpenChange(false);
      return;
    }
    try {
      await updateUser.mutateAsync({ id: target.id, body });
      onOpenChange(false);
    } catch (caught) {
      form.setError("root", {
        message: caught instanceof ApiError ? caught.message : "Could not save. Please try again.",
      });
    }
  };

  const lockedHint = (what: string) => {
    if (managed) return <ManagedInEklink href={eklinkLink} />;
    if (actor.role === "department_admin") return `Department admins cannot change the ${what}.`;
    if (actor.role === "institute_admin") return `Institute admins cannot change the ${what}.`;
    return `Only a super admin can change the ${what}.`;
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !isSubmitting && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] overflow-y-auto sm:w-full">
        <DialogHeader>
          <DialogTitle>Edit {target.full_name}</DialogTitle>
          <DialogDescription>
            {target.email}
            {target.login_id ? ` · ${target.login_id}` : ""}
            {target.sso ? " · signs in with EkLink" : ""}
          </DialogDescription>
        </DialogHeader>
        {managed && (
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
            <p className="font-medium">Managed in EkLink</p>
            <p className="mt-1 text-xs text-sky-800">
              Organization, institute, department, member type and the active flag come from
              EkLink. Here you can give or take TemplateOS admin roles.
            </p>
            {eklinkLink && <ManagedInEklink href={eklinkLink} className="mt-1 text-sky-800">Edit this person</ManagedInEklink>}
          </div>
        )}
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(submit)} noValidate>
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    disabled={!roleEditable || isSubmitting}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a role" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {roles.map((role) => (
                        <SelectItem key={role} value={role}>
                          {formatRole(role)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {roleEditable && managed && (
                    <p className="text-xs text-slate-500">
                      Admin roles are set here; the member role comes from EkLink.
                    </p>
                  )}
                  {!roleEditable && (
                    <p className="text-xs text-slate-500">
                      {actor.id === target.id
                        ? "You cannot change your own role."
                        : "You cannot change this user's role."}
                    </p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            {!memberRole && (
              <FormField
                control={form.control}
                name="member_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Member type</FormLabel>
                    <Select
                      value={field.value ?? NONE}
                      onValueChange={(next) => field.onChange(next === NONE ? null : next)}
                      disabled={isSubmitting || !memberTypeEditable}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>Not set</SelectItem>
                        {MEMBER_TYPES.map((type) => (
                          <SelectItem key={type} value={type}>
                            {formatRole(type)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {managed ? (
                      <ManagedInEklink href={eklinkLink} />
                    ) : (
                      <p className="text-xs text-slate-500">
                        What this administrator is besides their admin role. Faculty and staff
                        can be given approver jobs.
                      </p>
                    )}
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="organization_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Organization</FormLabel>
                  {orgEditable ? (
                    <IdSelect
                      value={field.value}
                      onChange={(organizationId) => {
                        field.onChange(organizationId);
                        // Institutes and departments never outlive their organization.
                        form.setValue("institute_id", null);
                        const department = form.getValues("department_id");
                        if (department !== null && departmentOrg.get(department) !== organizationId) {
                          form.setValue("department_id", null);
                        }
                      }}
                      disabled={isSubmitting}
                      noneLabel="No organization"
                      choices={organizations}
                    />
                  ) : (
                    <>
                      <Input value={target.organization ?? "—"} readOnly disabled />
                      <div className="text-xs text-slate-500">{lockedHint("organization")}</div>
                    </>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="institute_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Institute</FormLabel>
                  {instEditable ? (
                    <IdSelect
                      value={field.value}
                      onChange={(instituteId) => {
                        field.onChange(instituteId);
                        const department = form.getValues("department_id");
                        if (
                          department !== null &&
                          instituteId !== null &&
                          departmentInstitute.get(department) !== instituteId
                        ) {
                          form.setValue("department_id", null);
                        }
                      }}
                      disabled={isSubmitting || selectedOrg === null}
                      noneLabel="No institute"
                      choices={instChoices}
                    />
                  ) : (
                    <>
                      <Input value={target.institute ?? "—"} readOnly disabled />
                      <div className="text-xs text-slate-500">{lockedHint("institute")}</div>
                    </>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="department_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Department</FormLabel>
                  {deptEditable ? (
                    <IdSelect
                      value={field.value}
                      onChange={(departmentId) => {
                        field.onChange(departmentId);
                        // A department decides its institute.
                        if (departmentId !== null) {
                          const institute = departmentInstitute.get(departmentId);
                          if (institute != null) form.setValue("institute_id", institute);
                        }
                      }}
                      disabled={isSubmitting || selectedOrg === null}
                      noneLabel="No department"
                      choices={deptChoices}
                    />
                  ) : (
                    <>
                      <Input value={target.department ?? "—"} readOnly disabled />
                      <div className="text-xs text-slate-500">{lockedHint("department")}</div>
                    </>
                  )}
                  {deptEditable && selectedOrg === null && (
                    <p className="text-xs text-slate-500">Choose an organization first.</p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <FormItem>
                  <label className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 text-sm">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 accent-slate-900"
                      checked={field.value}
                      onChange={(event) => field.onChange(event.target.checked)}
                      disabled={!activeEditable || isSubmitting}
                    />
                    <span>
                      <span className="font-medium text-slate-900">Account active</span>
                      <span className="block text-xs text-slate-500">
                        {activeEditable
                          ? "A deactivated user cannot sign in. Their documents are kept and they can be reactivated."
                          : managed
                            ? "Managed in EkLink: deactivate or reactivate this person in EkLink."
                            : "You cannot deactivate your own account."}
                      </span>
                    </span>
                  </label>
                </FormItem>
              )}
            />

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
                Save changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
