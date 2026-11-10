import { useState } from "react";
import { Building2, ExternalLink, Pencil, Plus, Power, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { AdminQueryError } from "@/features/admin/AdminRoute";
import { ConfirmDialog } from "@/features/admin/ConfirmDialog";
import { FromEklinkBadge } from "@/features/admin/ManagedInEklink";
import { NameDialog } from "@/features/admin/NameDialog";
import {
  useCreateDepartment,
  useCreateInstitute,
  useCreateOrganization,
  useDeleteDepartment,
  useDeleteInstitute,
  useDeleteOrganization,
  useDepartments,
  useInstitutes,
  useOrganizations,
  useSyncStatus,
  useUpdateDepartment,
  useUpdateInstitute,
  useUpdateOrganization,
} from "@/hooks/queries";
import {
  canCreateUnder,
  canEditDirectoryRow,
  canManageDepartments,
  canManageInstitutes,
  canManageOrganizations,
  departmentsOf,
  institutesOf,
} from "@/lib/admin-permissions";
import type { Department, Institute, Organization } from "@/lib/api";
import { cn } from "@/lib/utils";

type Level = "organization" | "institute" | "department";
type Row = Organization | Institute | Department;

type NameTarget =
  | { kind: "new"; level: Level; parent?: Organization | Institute }
  | { kind: "edit"; level: Level; row: Row };

type DeleteTarget = { level: Level; row: Row };

function plural(count: number | undefined, word: string) {
  const n = count ?? 0;
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

const LEVEL_LABEL: Record<Level, string> = {
  organization: "organization",
  institute: "institute",
  department: "department",
};

interface ListPanelProps<T extends Row> {
  title: string;
  rows: T[];
  loading: boolean;
  activeId?: number | null;
  onSelect?: (id: number) => void;
  canManage: boolean;
  onNew?: () => void;
  newLabel: string;
  empty: string;
  describe: (row: T) => string;
  onEdit: (row: T) => void;
  onToggle: (row: T) => void;
  onDelete: (row: T) => void;
  /** EkLink Admin Console directory page, linked from rows mirrored from EkLink. */
  eklinkDirectoryUrl?: string | null;
}

function ListPanel<T extends Row>({
  title,
  rows,
  loading,
  activeId,
  onSelect,
  canManage,
  onNew,
  newLabel,
  empty,
  describe,
  onEdit,
  onToggle,
  onDelete,
  eklinkDirectoryUrl,
}: ListPanelProps<T>) {
  return (
    <section className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <h2 className="min-w-0 truncate text-sm font-semibold">{title}</h2>
        {canManage && onNew && (
          <Button size="sm" variant="outline" onClick={onNew}>
            <Plus className="h-4 w-4" /> {newLabel}
          </Button>
        )}
      </div>
      {loading ? (
        <div className="space-y-2 p-4">
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
        </div>
      ) : rows.length === 0 ? (
        <p className="p-6 text-center text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((row) => {
            const inactive = row.is_active === false;
            // Rows with an EkLink code are read-only here (changed in EkLink).
            const editable = canManage && canEditDirectoryRow(row);
            const fromEklink = !canEditDirectoryRow(row);
            return (
              <li
                key={row.id}
                className={cn(
                  "flex items-center gap-1 px-4 py-3",
                  row.id === activeId && "bg-slate-50",
                  inactive && "opacity-60",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left disabled:cursor-default"
                  onClick={() => onSelect?.(row.id)}
                  disabled={!onSelect}
                  aria-pressed={onSelect ? row.id === activeId : undefined}
                >
                  <div className="flex min-w-0 items-center gap-2 font-medium text-slate-900">
                    <span className="truncate">{row.name}</span>
                    {row.code && (
                      <Badge variant="outline" className="shrink-0 font-mono text-[10px]">
                        {row.code}
                      </Badge>
                    )}
                    {fromEklink && <FromEklinkBadge className="shrink-0 text-[10px]" />}
                    {inactive && (
                      <Badge variant="outline" className="shrink-0 border-red-200 text-red-700">
                        Inactive
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">{describe(row)}</p>
                </button>
                {fromEklink && canManage && eklinkDirectoryUrl && (
                  <Button variant="ghost" size="icon" asChild>
                    <a
                      href={eklinkDirectoryUrl}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Change ${row.name} in EkLink`}
                      title="Managed in EkLink: change it in EkLink"
                    >
                      <ExternalLink className="h-4 w-4 text-sky-700" />
                    </a>
                  </Button>
                )}
                {editable && (
                  <>
                    <Button variant="ghost" size="icon" aria-label={`Edit ${row.name}`} onClick={() => onEdit(row)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`${inactive ? "Reactivate" : "Deactivate"} ${row.name}`}
                      title={inactive ? "Reactivate" : "Deactivate"}
                      onClick={() => onToggle(row)}
                    >
                      <Power className={cn("h-4 w-4", inactive ? "text-emerald-600" : "text-amber-600")} />
                    </Button>
                    <Button variant="ghost" size="icon" aria-label={`Delete ${row.name}`} onClick={() => onDelete(row)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function AdminOrganizationsPage() {
  const { user } = useAuth();
  const organizations = useOrganizations();
  const institutes = useInstitutes();
  const departments = useDepartments();
  const sync = useSyncStatus();
  const eklinkDirectoryUrl = sync.data?.links.directory ?? null;
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null);
  const [selectedInstId, setSelectedInstId] = useState<number | null>(null);
  const [nameTarget, setNameTarget] = useState<NameTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const createOrganization = useCreateOrganization();
  const updateOrganization = useUpdateOrganization();
  const deleteOrganization = useDeleteOrganization();
  const createInstitute = useCreateInstitute();
  const updateInstitute = useUpdateInstitute();
  const deleteInstitute = useDeleteInstitute();
  const createDepartment = useCreateDepartment();
  const updateDepartment = useUpdateDepartment();
  const deleteDepartment = useDeleteDepartment();

  if (!user) return null;
  const isSuperAdmin = canManageOrganizations(user.role);
  const isInstituteScoped = user.role === "institute_admin" || user.role === "department_admin";

  // Super admins browse every organization; everyone else sees only their own.
  const visibleOrganizations = (organizations.data ?? []).filter(
    (organization) => isSuperAdmin || organization.id === user.organization_id,
  );
  const activeOrgId = isSuperAdmin
    ? (selectedOrgId ?? visibleOrganizations[0]?.id ?? null)
    : user.organization_id;
  const activeOrg = visibleOrganizations.find((organization) => organization.id === activeOrgId) ?? null;

  const orgInstitutes = institutesOf(institutes.data ?? [], activeOrgId);
  const activeInstId = isInstituteScoped
    ? (user.institute_id ?? null)
    : (orgInstitutes.some((institute) => institute.id === selectedInstId)
        ? selectedInstId
        : (orgInstitutes[0]?.id ?? null));
  const activeInst = orgInstitutes.find((institute) => institute.id === activeInstId) ?? null;
  const instDepartments = departmentsOf(departments.data ?? [], activeOrgId, activeInstId);

  const mayManageInstitutes = canManageInstitutes(user, activeOrgId);
  const mayManageDepartments = canManageDepartments(user, activeOrgId, activeInstId);

  const queryError = organizations.error ?? institutes.error ?? departments.error;
  if (queryError && !organizations.data) {
    return <AdminQueryError error={queryError} onRetry={() => void organizations.refetch()} />;
  }

  const updateFor = (level: Level) =>
    level === "organization"
      ? updateOrganization
      : level === "institute"
        ? updateInstitute
        : updateDepartment;

  const toggle = (level: Level, row: Row) =>
    void updateFor(level).mutateAsync({ id: row.id, body: { is_active: row.is_active === false } });

  const nameDialog = (() => {
    if (!nameTarget) return null;
    const what = LEVEL_LABEL[nameTarget.level];
    if (nameTarget.kind === "edit") {
      const { row, level } = nameTarget;
      return {
        title: `Edit ${what}`,
        description: "Users and templates linked to it show the new name.",
        label: `${what[0].toUpperCase()}${what.slice(1)} name`,
        submitLabel: "Save",
        initialName: row.name,
        initialCode: row.code ?? null,
        onSubmit: (name: string, code: string | null) =>
          updateFor(level).mutateAsync({ id: row.id, body: { name, code } }),
      };
    }
    const parent = nameTarget.parent;
    return {
      title: parent ? `New ${what} in ${parent.name}` : `New ${what}`,
      description: undefined,
      label: `${what[0].toUpperCase()}${what.slice(1)} name`,
      submitLabel: "Create",
      initialName: "",
      initialCode: null,
      onSubmit: (name: string, code: string | null) => {
        if (nameTarget.level === "organization") return createOrganization.mutateAsync({ name, code });
        if (nameTarget.level === "institute") {
          return createInstitute.mutateAsync({ name, code, organizationId: parent?.id });
        }
        const institute = parent as Institute | undefined;
        return createDepartment.mutateAsync({
          name,
          code,
          instituteId: institute?.id,
          organizationId: institute?.organization_id,
        });
      },
    };
  })();

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold">Organizations, institutes &amp; departments</h1>
          <p className="mt-1 text-sm text-slate-600">
            {isSuperAdmin
              ? "The directory users and templates belong to: organization → institute → department."
              : isInstituteScoped
                ? "Your institute's departments."
                : "Your organization's institutes and departments."}{" "}
            Entries with a code (for example SIU, SIT, CSE) come from EkLink and are changed
            there; entries without a code are local to TemplateOS. Deactivate entries instead of
            deleting them once they are in use.
          </p>
          {eklinkDirectoryUrl && (
            <a
              href={eklinkDirectoryUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-sky-700 hover:underline"
            >
              Open the EkLink directory <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
        </div>
        {isSuperAdmin && (
          <Button onClick={() => setNameTarget({ kind: "new", level: "organization" })}>
            <Plus className="h-4 w-4" /> New organization
          </Button>
        )}
      </div>

      <div
        className={cn(
          "grid gap-6",
          isSuperAdmin ? "2xl:grid-cols-3" : !isInstituteScoped ? "xl:grid-cols-2" : "",
        )}
      >
        {isSuperAdmin && (
          <ListPanel<Organization>
            title="Organizations"
            rows={visibleOrganizations}
            loading={organizations.isPending}
            activeId={activeOrgId}
            onSelect={(id) => {
              setSelectedOrgId(id);
              setSelectedInstId(null);
            }}
            canManage
            newLabel="New"
            empty="No organizations yet."
            describe={(row) =>
              `${plural(row.institute_count, "institute")} · ${plural(row.department_count, "department")} · ${plural(row.user_count, "user")}`
            }
            onEdit={(row) => setNameTarget({ kind: "edit", level: "organization", row })}
            onToggle={(row) => toggle("organization", row)}
            onDelete={(row) => setDeleteTarget({ level: "organization", row })}
            eklinkDirectoryUrl={eklinkDirectoryUrl}
          />
        )}

        {!isInstituteScoped && (
          <ListPanel<Institute>
            title={activeOrg ? `Institutes of ${activeOrg.name}` : "Institutes"}
            rows={orgInstitutes}
            loading={institutes.isPending}
            activeId={activeInstId}
            onSelect={setSelectedInstId}
            canManage={Boolean(activeOrg) && mayManageInstitutes}
            onNew={
              activeOrg && canCreateUnder(activeOrg)
                ? () => setNameTarget({ kind: "new", level: "institute", parent: activeOrg })
                : undefined
            }
            newLabel="New institute"
            empty={
              activeOrg
                ? "No institutes yet."
                : "Your profile has no organization. Ask a super admin to set it."
            }
            describe={(row) =>
              `${plural(row.department_count, "department")} · ${plural(row.user_count, "user")}`
            }
            onEdit={(row) => setNameTarget({ kind: "edit", level: "institute", row })}
            onToggle={(row) => toggle("institute", row)}
            onDelete={(row) => setDeleteTarget({ level: "institute", row })}
            eklinkDirectoryUrl={eklinkDirectoryUrl}
          />
        )}

        <ListPanel<Department>
          title={activeInst ? `Departments of ${activeInst.name}` : "Departments"}
          rows={instDepartments}
          loading={departments.isPending}
          canManage={Boolean(activeInst) && mayManageDepartments}
          onNew={
            activeInst && canCreateUnder(activeInst)
              ? () => setNameTarget({ kind: "new", level: "department", parent: activeInst })
              : undefined
          }
          newLabel="New department"
          empty={
            activeInst
              ? "No departments yet."
              : activeOrg
                ? "Create or choose an institute to see its departments."
                : "Nothing to show yet."
          }
          describe={(row) => plural(row.user_count, "user")}
          onEdit={(row) => setNameTarget({ kind: "edit", level: "department", row })}
          onToggle={(row) => toggle("department", row)}
          onDelete={(row) => setDeleteTarget({ level: "department", row })}
          eklinkDirectoryUrl={eklinkDirectoryUrl}
        />
      </div>

      {!activeOrg && !organizations.isPending && isSuperAdmin && visibleOrganizations.length === 0 && (
        <div className="p-8 text-center text-sm text-slate-500">
          <Building2 className="mx-auto mb-2 h-6 w-6 text-slate-400" />
          Create an organization to add institutes and departments.
        </div>
      )}

      {nameDialog && (
        <NameDialog
          open
          onOpenChange={(open) => !open && setNameTarget(null)}
          title={nameDialog.title}
          description={nameDialog.description}
          label={nameDialog.label}
          initialName={nameDialog.initialName}
          initialCode={nameDialog.initialCode}
          submitLabel={nameDialog.submitLabel}
          onSubmit={nameDialog.onSubmit}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          title={`Delete ${LEVEL_LABEL[deleteTarget.level]}?`}
          description={
            <>
              <span className="font-medium text-slate-900">{deleteTarget.row.name}</span> will be
              deleted. Anything still used by users, templates or sub-units cannot be deleted:
              deactivate it instead.
            </>
          }
          confirmLabel="Delete"
          onConfirm={async () => {
            const { level, row } = deleteTarget;
            if (level === "organization") {
              await deleteOrganization.mutateAsync(row.id);
              if (selectedOrgId === row.id) setSelectedOrgId(null);
            } else if (level === "institute") {
              await deleteInstitute.mutateAsync(row.id);
              if (selectedInstId === row.id) setSelectedInstId(null);
            } else {
              await deleteDepartment.mutateAsync(row.id);
            }
          }}
        />
      )}
    </div>
  );
}
