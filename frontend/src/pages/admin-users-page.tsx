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
import { useAdminUsers, useDepartments, useOrganizations } from "@/hooks/queries";
import { USER_ROLES, canEditUser, departmentsOf, type Member } from "@/lib/admin-permissions";
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
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminUser | null>(null);

  useEffect(() => setPage(1), [search, role, organizationId, departmentId]);

  const isSuperAdmin = user?.role === "super_admin";
  const isDeptAdmin = user?.role === "department_admin";
  const organizations = useOrganizations();
  const departments = useDepartments();

  const users = useAdminUsers({
    search: search || undefined,
    role: role === ALL ? undefined : role,
    organization_id: organizationId ?? undefined,
    department_id: departmentId ?? undefined,
    page,
    limit: PAGE_SIZE,
  });

  // Department filter: the chosen organization's (super admin) or their own.
  const filterOrg = isSuperAdmin ? organizationId : user?.organization_id ?? null;
  const departmentFilterChoices = useMemo(
    () => departmentsOf(departments.data ?? [], filterOrg),
    [departments.data, filterOrg],
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
            ? "Every account on TemplateOS. Assign roles, organizations and departments."
            : isDeptAdmin
              ? "People in your department. You can change their role."
              : "People in your organization. Assign roles and departments."}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="relative sm:col-span-2 lg:col-span-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search name or email"
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
            {USER_ROLES.map((value) => (
              <SelectItem key={value} value={value}>
                {formatRole(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {isSuperAdmin && (
          <Select
            value={organizationId === null ? ALL : String(organizationId)}
            onValueChange={(next) => {
              setOrganizationId(next === ALL ? null : Number(next));
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
                      <td colSpan={5} className="px-4 py-4">
                        <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))}
                {!users.isPending && rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-slate-500">
                      <UsersRound className="mx-auto mb-2 h-6 w-6 text-slate-400" />
                      No users match these filters.
                    </td>
                  </tr>
                )}
                {rows.map((row) => {
                  const editable = canEditUser(actor, row);
                  return (
                    <tr key={row.id} className="align-top">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-900">
                          {row.full_name}
                          {row.id === user.id && (
                            <span className="ml-2 text-xs font-normal text-slate-500">(you)</span>
                          )}
                        </p>
                        <p className="break-all text-xs text-slate-500">{row.email}</p>
                        <p className="mt-1 text-xs text-slate-500 md:hidden">
                          {[row.organization, row.department].filter(Boolean).join(" · ") || "—"}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary">{formatRole(row.role)}</Badge>
                      </td>
                      <td className="hidden px-4 py-3 text-slate-700 md:table-cell">
                        {row.organization ?? <span className="text-slate-400">—</span>}
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
        departments={departments.data ?? []}
        onOpenChange={(open) => !open && setEditing(null)}
      />
    </div>
  );
}
