import { request } from "./client";
import type {
  AdminUser,
  AdminUserList,
  AdminUserListParams,
  AdminUserUpdate,
  ApproverAssignment,
  ApproverAssignmentCreate,
  ApproverAssignmentList,
  Department,
  DirectoryUpdate,
  Institute,
  Organization,
  SyncRunResult,
  SyncStatus,
} from "./types";

function toQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** /admin: users, the organization -> institute -> department directory and approvers. */
export const adminApi = {
  listUsers: (params: AdminUserListParams = {}) =>
    request<AdminUserList>(`/admin/users${toQuery(params)}`),
  updateUser: (id: number, body: AdminUserUpdate) =>
    request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  listOrganizations: () => request<Organization[]>("/admin/organizations"),
  createOrganization: (name: string, code?: string | null) =>
    request<Organization>("/admin/organizations", {
      method: "POST",
      body: JSON.stringify({ name, code: code || null }),
    }),
  updateOrganization: (id: number, body: DirectoryUpdate) =>
    request<Organization>(`/admin/organizations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  renameOrganization: (id: number, name: string) =>
    request<Organization>(`/admin/organizations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteOrganization: (id: number) =>
    request<void>(`/admin/organizations/${id}`, { method: "DELETE" }),

  /** super_admin: all; others: their organization's (institute / department admins: their own). */
  listInstitutes: (organizationId?: number) =>
    request<Institute[]>(`/admin/institutes${toQuery({ organization_id: organizationId })}`),
  createInstitute: (name: string, organizationId?: number, code?: string | null) =>
    request<Institute>("/admin/institutes", {
      method: "POST",
      body: JSON.stringify({ name, organization_id: organizationId, code: code || null }),
    }),
  updateInstitute: (id: number, body: DirectoryUpdate) =>
    request<Institute>(`/admin/institutes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteInstitute: (id: number) => request<void>(`/admin/institutes/${id}`, { method: "DELETE" }),

  /** super_admin: every department (or one organization's); others: their own scope's. */
  listDepartments: (organizationId?: number) =>
    request<Department[]>(`/admin/departments${toQuery({ organization_id: organizationId })}`),
  createDepartment: (
    name: string,
    organizationId?: number,
    instituteId?: number,
    code?: string | null,
  ) =>
    request<Department>("/admin/departments", {
      method: "POST",
      body: JSON.stringify({
        name,
        organization_id: organizationId,
        institute_id: instituteId,
        code: code || null,
      }),
    }),
  updateDepartment: (id: number, body: DirectoryUpdate) =>
    request<Department>(`/admin/departments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  renameDepartment: (id: number, name: string) =>
    request<Department>(`/admin/departments/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteDepartment: (id: number) =>
    request<void>(`/admin/departments/${id}`, { method: "DELETE" }),

  listApprovers: (params: { current_only?: boolean; user_id?: number } = {}) =>
    request<ApproverAssignmentList>(`/admin/approvers${toQuery(params)}`),
  createApprover: (body: ApproverAssignmentCreate) =>
    request<ApproverAssignment>("/admin/approvers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  endApprover: (id: number) =>
    request<ApproverAssignment>(`/admin/approvers/${id}/end`, { method: "POST" }),

  /** EkLink sync: status for any admin; run / full resync for super admins. */
  syncStatus: () => request<SyncStatus>("/admin/sync/status"),
  runSync: () => request<SyncRunResult>("/admin/sync/run", { method: "POST" }),
  fullResync: () => request<SyncRunResult>("/admin/sync/full", { method: "POST" }),
};
