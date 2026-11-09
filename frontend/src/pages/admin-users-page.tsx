import { useEffect, useMemo, useState } from "react";
import { Pencil, Search, UsersRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { AdminQueryError } from "@/features/admin/AdminRoute";
import { EditUserDialog } from "@/features/admin/EditUserDialog";
import {
  useAdminUsers,
  useDepartments,
  useInstitutes,
  useOrganizations,
  useSyncStatus,
} from "@/hooks/queries";
import {
  LEGACY_ROLES,
  USER_ROLES,
  canEditUser,
  departmentsOf,
  institutesOf,
  type Member,
} from "@/lib/admin-permissions";
import type { AdminUser } from "@/lib/api";
import { formatRole } from "@/lib/format";

const ALL = "all";
const PAGE_SIZE = 20;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function AdminUsersPage() {
  const { user } = useAuth();
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput.trim());
  const [role, setRole] = useState(ALL);
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [instituteId, setInstituteId] = useState<number | null>(null);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>(ALL);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminUser | null>(null);

  useEffect(
    () => setPage(1),
    [search, role, organizationId, instituteId, departmentId, status],
  );

  const isSuperAdmin = user?.role === "super_admin";
  const isOrgAdmin = user?.role === "org_admin";
  const isInstituteAdmin = user?.role === "institute_admin";
  const isDeptAdmin = user?.role === "department_admin";
  const organizations = useOrganizations();
  const institutes = useInstitutes();
  const departments = useDepartments();
  const sync = useSyncStatus();
  const eklinkUrl = sync.data?.eklink_url ?? null;

  const users = useAdminUsers({
    search: search || undefined,
    role: role === ALL ? undefined : role,
    organization_id: organizationId ?? undefined,
    institute_id: instituteId ?? undefined,
    department_id: departmentId ?? undefined,
    is_active: status === ALL ? undefined : status === "active",
    page,
    limit: PAGE_SIZE,
  });

  // Institute / department filters: the chosen organization's (super admin) or their own.
  const filterOrg = isSuperAdmin ? organizationId : user?.organization_id ?? null;
  const instituteFilterChoices = useMemo(
    () => institutesOf(institutes.data ?? [], filterOrg),
    [institutes.data, filterOrg],
  );
  const filterInstitute = isInstituteAdmin ? user?.institute_id ?? null : instituteId;
  const departmentFilterChoices = useMemo(
    () => departmentsOf(departments.data ?? [], filterOrg, filterInstitute),
    [departments.data, filterOrg, filterInstitute],
  );

  if (!user) return null;
  const actor: Member = user;
  const total = users.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = users.data?.users ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Users</h1>
        <p className="mt-1 text-sm text-slate-600">
          {isSuperAdmin
            ? "Every account on TemplateOS. Assign roles, organizations, institutes and departments."
            : isDeptAdmin
              ? "People in your department. You can change their role or deactivate them."
              : isInstituteAdmin
                ? "People in your institute. Assign roles and departments."
                : "People in your organization. Assign roles, institutes and departments."}
          {" "}Accounts are never deleted: deactivate them instead.
        </p>
        {sync.data?.enabled && (
          <p className="mt-2 text-sm text-slate-600">
            People marked EkLink are managed in EkLink: their organization, institute, department,
            member type and active status are changed there.{" "}
            {sync.data.links.users && (
              <a
                href={sync.data.links.users}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-sky-700 hover:underline"
              >
                Open EkLink people
              </a>
            )}
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <div className="relative sm:col-span-2 lg:col-span-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search name, email or login ID"
            aria-label="Search users"
            className="pl-9"
            maxLength={100}
          />
        </div>
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger aria-label="Filter by role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All roles</SelectItem>
            {[...USER_ROLES, ...LEGACY_ROLES].map((value) => (
              <SelectItem key={value} value={value}>
                {formatRole(value)}
                {LEGACY_ROLES.includes(value) ? " (old)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Deactivated</SelectItem>
          </SelectContent>
        </Select>
        {isSuperAdmin && (
          <Select
            value={organizationId === null ? ALL : String(organizationId)}
            onValueChange={(next) => {
              setOrganizationId(next === ALL ? null : Number(next));
              setInstituteId(null);
              setDepartmentId(null);
            }}
          >
            <SelectTrigger aria-label="Filter by organization">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All organizations</SelectItem>
              {(organizations.data ?? []).map((organization) => (
                <SelectItem key={organization.id} value={String(organization.id)}>
                  {organization.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {(isSuperAdmin || isOrgAdmin) && (
          <Select
            value={instituteId === null ? ALL : String(instituteId)}
            onValueChange={(next) => {
              setInstituteId(next === ALL ? null : Number(next));
              setDepartmentId(null);
            }}
            disabled={instituteFilterChoices.length === 0}
          >
            <SelectTrigger aria-label="Filter by institute">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>
                {filterOrg === null ? "Pick an organization for institutes" : "All institutes"}
              </SelectItem>
              {instituteFilterChoices.map((institute) => (
                <SelectItem key={institute.id} value={String(institute.id)}>
                  {institute.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {!isDeptAdmin && (
          <Select
            value={departmentId === null ? ALL : String(departmentId)}
            onValueChange={(next) => setDepartmentId(next === ALL ? null : Number(next))}
            disabled={departmentFilterChoices.length === 0}
          >
            <SelectTrigger aria-label="Filter by department">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>
                {filterOrg === null ? "Pick an organization for departments" : "All departments"}
              </SelectItem>
              {departmentFilterChoices.map((department) => (
                <SelectItem key={department.id} value={String(department.id)}>
                  {department.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {users.isError && !users.data ? (
        <AdminQueryError error={users.error} onRetry={() => void users.refetch()} />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-3">Name</th>
                  <th scope="col" className="px-4 py-3">Role</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Organization</th>
                  <th scope="col" className="hidden px-4 py-3 lg:table-cell">Institute</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Department</th>
                  <th scope="col" className="px-4 py-3 text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.isPending &&
                  Array.from({ length: 5 }).map((_, index) => (
                    <tr key={`skeleton-${index}`}>
                      <td colSpan={6} className="px-4 py-4">
                        <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))}
                {!users.isPending && rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                      <UsersRound className="mx-auto mb-2 h-6 w-6 text-slate-400" />
                      No users match these filters.
                    </td>
                  </tr>
                )}
                {rows.map((row) => {
                  const editable = canEditUser(actor, row);
                  return (
                    <tr
                      key={row.id}
                      className={row.is_active === false ? "bg-slate-50 align-top text-slate-500" : "align-top"}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-900">
                          {row.full_name}
                          {row.id === user.id && (
                            <span className="ml-2 text-xs font-normal text-slate-500">(you)</span>
                          )}
                        </p>
                        <p className="break-all text-xs text-slate-500">
                          {row.email}
                          {row.login_id && <span className="ml-1 font-mono">· {row.login_id}</span>}
                        </p>
                        <p className="mt-1 text-xs text-slate-500 md:hidden">
                          {[row.organization, row.institute, row.department]
                            .filter(Boolean)
                            .join(" · ") || "—"}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          <Badge variant="secondary">{formatRole(row.role)}</Badge>
                          {row.is_active === false && (
                            <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">
                              Deactivated
                            </Badge>
                          )}
                          {(row.sso || row.managed_by_eklink) && (
                            <Badge
                              variant="outline"
                              className="border-sky-200 bg-sky-50 text-sky-700"
                              title={row.managed_by_eklink ? "Managed in EkLink" : "Signs in with EkLink"}
                            >
                              EkLink
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="hidden px-4 py-3 text-slate-700 md:table-cell">
                        {row.organization ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="hidden px-4 py-3 text-slate-700 lg:table-cell">
                        {row.institute ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="hidden px-4 py-3 text-slate-700 md:table-cell">
                        {row.department ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditing(row)}
                          disabled={!editable}
                          title={editable ? "Edit user" : "You cannot edit this user"}
                        >
                          <Pencil className="h-4 w-4" />
                          <span className="hidden sm:inline">Edit</span>
                          <span className="sr-only sm:hidden">Edit {row.full_name}</span>
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-col items-center justify-between gap-2 border-t border-slate-200 px-4 py-3 text-sm text-slate-600 sm:flex-row">
            <span>
              {total} user{total === 1 ? "" : "s"}
              {users.isFetching && !users.isPending && " · updating…"}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page <= 1}
              >
                Previous
              </Button>
              <span>
                Page {page} of {pageCount}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                disabled={page >= pageCount}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      )}

      <EditUserDialog
        actor={actor}
        target={editing}
        organizations={organizations.data ?? []}
        institutes={institutes.data ?? []}
        departments={departments.data ?? []}
        eklinkUrl={eklinkUrl}
        onOpenChange={(open) => !open && setEditing(null)}
      />
    </div>
  );
}
