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
  buildUserUpdate,
  canChangeDepartment,
  canChangeOrganization,
  canChangeRole,
  departmentsOf,
  roleChoices,
  validateUserEdit,
  type Member,
} from "@/lib/admin-permissions";
import { ApiError, type AdminUser, type Department, type Organization } from "@/lib/api";
import { formatRole } from "@/lib/format";

const NONE = "none";

const editSchema = z.object({
  role: z.string().min(1),
  organization_id: z.number().int().nullable(),
  department_id: z.number().int().nullable(),
});

type EditValues = z.infer<typeof editSchema>;

interface EditUserDialogProps {
  actor: Member;
  target: AdminUser | null;
  organizations: Organization[];
  departments: Department[];
  onOpenChange: (open: boolean) => void;
}

export function EditUserDialog({
  actor,
  target,
  organizations,
  departments,
  onOpenChange,
}: EditUserDialogProps) {
  const open = target !== null;
  const updateUser = useUpdateAdminUser();
  const departmentOrg = useMemo(
    () => new Map(departments.map((department) => [department.id, department.organization_id])),
    [departments],
  );
  const schema = useMemo(
    () =>
      editSchema.superRefine((values, ctx) => {
        for (const [path, message] of Object.entries(validateUserEdit(values, departmentOrg))) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
        }
      }),
    [departmentOrg],
  );

  const form = useForm<EditValues>({
    resolver: zodResolver(schema),
    defaultValues: { role: "", organization_id: null, department_id: null },
  });
  const { isSubmitting, errors } = form.formState;

  useEffect(() => {
    if (target) {
      form.reset({
        role: target.role,
        organization_id: target.organization_id,
        department_id: target.department_id,
      });
    }
  }, [target, form]);

  if (!target) return null;

  const roleEditable = canChangeRole(actor, target);
  const orgEditable = canChangeOrganization(actor);
  const deptEditable = canChangeDepartment(actor);
  const roles = roleChoices(actor, target);
  const selectedOrg = form.watch("organization_id");
  const deptChoices = departmentsOf(departments, selectedOrg);

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

  const lockedHint = (what: string) =>
    actor.role === "department_admin"
      ? `Department admins cannot change the ${what}.`
      : `Only a super admin can change the ${what}.`;

  return (
    <Dialog open={open} onOpenChange={(next) => !isSubmitting && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] overflow-y-auto sm:w-full">
        <DialogHeader>
          <DialogTitle>Edit {target.full_name}</DialogTitle>
          <DialogDescription>{target.email}</DialogDescription>
        </DialogHeader>
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

            <FormField
              control={form.control}
              name="organization_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Organization</FormLabel>
                  {orgEditable ? (
                    <Select
                      value={field.value === null ? NONE : String(field.value)}
                      onValueChange={(next) => {
                        const organizationId = next === NONE ? null : Number(next);
                        field.onChange(organizationId);
                        // A department never outlives its organization.
                        const department = form.getValues("department_id");
                        if (department !== null && departmentOrg.get(department) !== organizationId) {
                          form.setValue("department_id", null);
                        }
                      }}
                      disabled={isSubmitting}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>No organization</SelectItem>
                        {organizations.map((organization) => (
                          <SelectItem key={organization.id} value={String(organization.id)}>
                            {organization.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <>
                      <Input value={target.organization ?? "—"} readOnly disabled />
                      <p className="text-xs text-slate-500">{lockedHint("organization")}</p>
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
                    <Select
                      value={field.value === null ? NONE : String(field.value)}
                      onValueChange={(next) => field.onChange(next === NONE ? null : Number(next))}
                      disabled={isSubmitting || selectedOrg === null}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>No department</SelectItem>
                        {deptChoices.map((department) => (
                          <SelectItem key={department.id} value={String(department.id)}>
                            {department.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <>
                      <Input value={target.department ?? "—"} readOnly disabled />
                      <p className="text-xs text-slate-500">{lockedHint("department")}</p>
                    </>
                  )}
                  {deptEditable && selectedOrg === null && (
                    <p className="text-xs text-slate-500">Choose an organization first.</p>
                  )}
                  <FormMessage />
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
