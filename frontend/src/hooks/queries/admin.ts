import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/context/auth-context";
import {
  adminApi,
  authApi,
  type AdminUser,
  type AdminUserListParams,
  type AdminUserUpdate,
  type ApiError,
  type ProfileUpdate,
} from "@/lib/api";
import { adminKeys, templateKeys } from "@/lib/query/keys";

// ── queries ────────────────────────────────────────────────────────────────

/** One page of GET /admin/users (scoped by the server to what the caller may see). */
export function useAdminUsers(params: AdminUserListParams, enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.listUsers>>, ApiError>({
    queryKey: adminKeys.userList(params),
    queryFn: () => adminApi.listUsers(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Every organization (any signed-in user may list them). */
export function useOrganizations(enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.listOrganizations>>, ApiError>({
    queryKey: adminKeys.organizations(),
    queryFn: () => adminApi.listOrganizations(),
    enabled,
    staleTime: 60_000,
  });
}

/** super_admin: all departments (or one organization's); others: their own organization's. */
export function useDepartments(organizationId?: number, enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.listDepartments>>, ApiError>({
    queryKey: adminKeys.departments(organizationId),
    queryFn: () => adminApi.listDepartments(organizationId),
    enabled,
    staleTime: 60_000,
  });
}

// ── mutations ──────────────────────────────────────────────────────────────

export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  const { user: me, refreshUser } = useAuth();
  return useMutation<AdminUser, ApiError, { id: number; body: AdminUserUpdate }>({
    mutationFn: ({ id, body }) => adminApi.updateUser(id, body),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      // Membership counts on the directory pages change with the user.
      void queryClient.invalidateQueries({ queryKey: adminKeys.organizations() });
      void queryClient.invalidateQueries({ queryKey: adminKeys.departmentLists() });
      if (me && updated.id === me.id) {
        void refreshUser();
        // Their own scope decides what they may publish and see.
        void queryClient.invalidateQueries({ queryKey: templateKeys.all });
      }
    },
  });
}

/**
 * Directory changes: organizations / departments feed the admin pages, the
 * audience pickers (access-options) and, on rename, the names shown on
 * template badges and on the current user's profile.
 */
function useInvalidateDirectory() {
  const queryClient = useQueryClient();
  const { refreshUser } = useAuth();
  return (options: { renamed?: boolean } = {}) => {
    void queryClient.invalidateQueries({ queryKey: adminKeys.organizations() });
    void queryClient.invalidateQueries({ queryKey: adminKeys.departmentLists() });
    void queryClient.invalidateQueries({ queryKey: templateKeys.accessOptions() });
    if (options.renamed) {
      void queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      void queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: templateKeys.details() });
      void refreshUser();
    }
  };
}

export function useCreateOrganization() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: (name: string) => adminApi.createOrganization(name),
    onSuccess: () => invalidate(),
  });
}

export function useRenameOrganization() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      adminApi.renameOrganization(id, name),
    onSuccess: () => invalidate({ renamed: true }),
  });
}

export function useDeleteOrganization() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: (id: number) => adminApi.deleteOrganization(id),
    onSuccess: () => invalidate(),
  });
}

export function useCreateDepartment() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ name, organizationId }: { name: string; organizationId?: number }) =>
      adminApi.createDepartment(name, organizationId),
    onSuccess: () => invalidate(),
  });
}

export function useRenameDepartment() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => adminApi.renameDepartment(id, name),
    onSuccess: () => invalidate({ renamed: true }),
  });
}

export function useDeleteDepartment() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: (id: number) => adminApi.deleteDepartment(id),
    onSuccess: () => invalidate(),
  });
}

// ── self-service profile ───────────────────────────────────────────────────

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  const { setCurrentUser } = useAuth();
  return useMutation({
    mutationFn: (body: ProfileUpdate) => authApi.updateMe(body),
    onSuccess: (user) => {
      setCurrentUser(user);
      // Admin lists show names / job titles.
      void queryClient.invalidateQueries({ queryKey: adminKeys.users() });
    },
  });
}
