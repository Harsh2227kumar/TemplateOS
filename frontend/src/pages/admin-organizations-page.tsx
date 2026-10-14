import { useState } from "react";
import { Building2, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { AdminQueryError } from "@/features/admin/AdminRoute";
import { ConfirmDialog } from "@/features/admin/ConfirmDialog";
import { NameDialog } from "@/features/admin/NameDialog";
import {
  useCreateDepartment,
  useCreateOrganization,
  useDeleteDepartment,
  useDeleteOrganization,
  useDepartments,
  useOrganizations,
  useRenameDepartment,
  useRenameOrganization,
} from "@/hooks/queries";
import {
  canManageDepartments,
  canManageOrganizations,
  departmentsOf,
} from "@/lib/admin-permissions";
import type { Department, Organization } from "@/lib/api";
import { cn } from "@/lib/utils";

type NameTarget =
  | { kind: "new-organization" }
  | { kind: "rename-organization"; organization: Organization }
  | { kind: "new-department"; organization: Organization }
  | { kind: "rename-department"; department: Department };

type DeleteTarget =
  | { kind: "organization"; organization: Organization }
  | { kind: "department"; department: Department };

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export function AdminOrganizationsPage() {
  const { user } = useAuth();
  const organizations = useOrganizations();
  const departments = useDepartments();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [nameTarget, setNameTarget] = useState<NameTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const createOrganization = useCreateOrganization();
  const renameOrganization = useRenameOrganization();
  const deleteOrganization = useDeleteOrganization();
  const createDepartment = useCreateDepartment();
  const renameDepartment = useRenameDepartment();
  const deleteDepartment = useDeleteDepartment();

  if (!user) return null;
  const isSuperAdmin = canManageOrganizations(user.role);

  // Super admins browse every organization; everyone else sees only their own.
  const visibleOrganizations = (organizations.data ?? []).filter(
    (organization) => isSuperAdmin || organization.id === user.organization_id,
  );
  const activeId = isSuperAdmin
    ? (selectedId ?? visibleOrganizations[0]?.id ?? null)
    : user.organization_id;
  const active = visibleOrganizations.find((organization) => organization.id === activeId) ?? null;
  const activeDepartments = departmentsOf(departments.data ?? [], activeId);
  const mayManageDepartments = canManageDepartments(user, activeId);

  const queryError = organizations.error ?? departments.error;
  if (queryError && !organizations.data) {
    return <AdminQueryError error={queryError} onRetry={() => void organizations.refetch()} />;
  }

  const nameDialog = (() => {
    if (!nameTarget) return null;
    switch (nameTarget.kind) {
      case "new-organization":
        return {
          title: "New organization",
          label: "Organization name",
          submitLabel: "Create",
          initialName: "",
          onSubmit: (name: string) => createOrganization.mutateAsync(name),
        };
      case "rename-organization":
        return {
          title: "Rename organization",
          description: "Users and templates linked to it show the new name.",
          label: "Organization name",
          submitLabel: "Rename",
          initialName: nameTarget.organization.name,
          onSubmit: (name: string) =>
            renameOrganization.mutateAsync({ id: nameTarget.organization.id, name }),
        };
      case "new-department":
        return {
          title: `New department in ${nameTarget.organization.name}`,
          label: "Department name",
          submitLabel: "Create",
          initialName: "",
          onSubmit: (name: string) =>
            createDepartment.mutateAsync({ name, organizationId: nameTarget.organization.id }),
        };
      case "rename-department":
        return {
          title: "Rename department",
          description: "Users and templates linked to it show the new name.",
          label: "Department name",
          submitLabel: "Rename",
          initialName: nameTarget.department.name,
          onSubmit: (name: string) =>
            renameDepartment.mutateAsync({ id: nameTarget.department.id, name }),
        };
    }
  })();

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold">Organizations &amp; departments</h1>
          <p className="mt-1 text-sm text-slate-600">
            {isSuperAdmin
              ? "The organizations and departments users and templates are assigned to."
              : "Your organization's departments."}
          </p>
        </div>
        {isSuperAdmin && (
          <Button onClick={() => setNameTarget({ kind: "new-organization" })}>
            <Plus className="h-4 w-4" /> New organization
          </Button>
        )}
      </div>

      <div className={cn("grid gap-6", isSuperAdmin && "lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]")}>
        {isSuperAdmin && (
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold">
              Organizations
            </h2>
            {organizations.isPending ? (
              <div className="space-y-2 p-4">
                <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
              </div>
            ) : visibleOrganizations.length === 0 ? (
              <p className="p-6 text-center text-sm text-slate-500">No organizations yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {visibleOrganizations.map((organization) => (
                  <li
                    key={organization.id}
                    className={cn(
                      "flex items-center gap-2 px-4 py-3",
                      organization.id === activeId && "bg-slate-50",
                    )}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => setSelectedId(organization.id)}
                      aria-pressed={organization.id === activeId}
                    >
                      <p className="truncate font-medium text-slate-900">{organization.name}</p>
                      <p className="text-xs text-slate-500">
                        {plural(organization.department_count, "department")} ·{" "}
                        {plural(organization.user_count, "user")}
                      </p>
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Rename ${organization.name}`}
                      onClick={() => setNameTarget({ kind: "rename-organization", organization })}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${organization.name}`}
                      onClick={() => setDeleteTarget({ kind: "organization", organization })}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <h2 className="min-w-0 truncate text-sm font-semibold">
              {active ? `Departments of ${active.name}` : "Departments"}
            </h2>
            {active && mayManageDepartments && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setNameTarget({ kind: "new-department", organization: active })}
              >
                <Plus className="h-4 w-4" /> New department
              </Button>
            )}
          </div>
          {!active ? (
            <div className="p-8 text-center text-sm text-slate-500">
              <Building2 className="mx-auto mb-2 h-6 w-6 text-slate-400" />
              {isSuperAdmin
                ? "Create an organization to add departments."
                : "Your profile has no organization. Ask a super admin to set it."}
            </div>
          ) : departments.isPending ? (
            <div className="space-y-2 p-4">
              <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
            </div>
          ) : activeDepartments.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-500">No departments yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {activeDepartments.map((department) => (
                <li key={department.id} className="flex items-center gap-2 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-slate-900">{department.name}</p>
                    <p className="text-xs text-slate-500">{plural(department.user_count, "user")}</p>
                  </div>
                  {mayManageDepartments && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Rename ${department.name}`}
                        onClick={() => setNameTarget({ kind: "rename-department", department })}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${department.name}`}
                        onClick={() => setDeleteTarget({ kind: "department", department })}
                      >
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {nameDialog && (
        <NameDialog
          open
          onOpenChange={(open) => !open && setNameTarget(null)}
          title={nameDialog.title}
          description={"description" in nameDialog ? nameDialog.description : undefined}
          label={nameDialog.label}
          initialName={nameDialog.initialName}
          submitLabel={nameDialog.submitLabel}
          onSubmit={nameDialog.onSubmit}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          title={
            deleteTarget.kind === "organization" ? "Delete organization?" : "Delete department?"
          }
          description={
            deleteTarget.kind === "organization" ? (
              <>
                <span className="font-medium text-slate-900">
                  {deleteTarget.organization.name}
                </span>{" "}
                and its unused departments will be deleted. Organizations still used by users or
                templates cannot be deleted.
              </>
            ) : (
              <>
                <span className="font-medium text-slate-900">{deleteTarget.department.name}</span>{" "}
                will be deleted. Departments still used by users or templates cannot be deleted.
              </>
            )
          }
          confirmLabel="Delete"
          onConfirm={async () => {
            if (deleteTarget.kind === "organization") {
              await deleteOrganization.mutateAsync(deleteTarget.organization.id);
              if (selectedId === deleteTarget.organization.id) setSelectedId(null);
            } else {
              await deleteDepartment.mutateAsync(deleteTarget.department.id);
            }
          }}
        />
      )}
    </div>
  );
}
