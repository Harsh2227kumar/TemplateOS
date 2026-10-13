import { request } from "./client";
import type {
  AdminUser,
  AdminUserList,
  AdminUserListParams,
  AdminUserUpdate,
  Department,
  Organization,
} from "./types";

function toQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** /admin: user management and the organization / department directory. */
export const adminApi = {
  listUsers: (params: AdminUserListParams = {}) =>
    request<AdminUserList>(`/admin/users${toQuery(params)}`),
  updateUser: (id: number, body: AdminUserUpdate) =>
    request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  listOrganizations: () => request<Organization[]>("/admin/organizations"),
  createOrganization: (name: string) =>
    request<Organization>("/admin/organizations", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  renameOrganization: (id: number, name: string) =>
    request<Organization>(`/admin/organizations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteOrganization: (id: number) =>
    request<void>(`/admin/organizations/${id}`, { method: "DELETE" }),

  /** super_admin: every department (or one organization's); others: their own organization's. */
  listDepartments: (organizationId?: number) =>
    request<Department[]>(`/admin/departments${toQuery({ organization_id: organizationId })}`),
  createDepartment: (name: string, organizationId?: number) =>
    request<Department>("/admin/departments", {
      method: "POST",
      body: JSON.stringify({ name, organization_id: organizationId }),
    }),
  renameDepartment: (id: number, name: string) =>
    request<Department>(`/admin/departments/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteDepartment: (id: number) =>
    request<void>(`/admin/departments/${id}`, { method: "DELETE" }),
};
