import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/context/auth-context";
import {
  adminApi,
  authApi,
  type AdminUser,
  type AdminUserListParams,
  type AdminUserUpdate,
  type ApiError,
  type ApproverAssignmentCreate,
  type DirectoryUpdate,
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

/** super_admin: all institutes (or one organization's); others: their own scope's. */
export function useInstitutes(organizationId?: number, enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.listInstitutes>>, ApiError>({
    queryKey: adminKeys.institutes(organizationId),
    queryFn: () => adminApi.listInstitutes(organizationId),
    enabled,
    staleTime: 60_000,
  });
}

/** Approver assignments inside the caller's admin scope. */
export function useApprovers(currentOnly = true, enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.listApprovers>>, ApiError>({
    queryKey: adminKeys.approvers({ current_only: currentOnly }),
    queryFn: () => adminApi.listApprovers({ current_only: currentOnly }),
    enabled,
  });
}

/** EkLink sync status (any admin). Also tells the admin pages whether EkLink owns the data. */
export function useSyncStatus(enabled = true) {
  return useQuery<Awaited<ReturnType<typeof adminApi.syncStatus>>, ApiError>({
    queryKey: adminKeys.syncStatus(),
    queryFn: () => adminApi.syncStatus(),
    enabled,
    staleTime: 30_000,
  });
}

// ── mutations ──────────────────────────────────────────────────────────────

/** "Sync now" (changes) or "Full resync" (snapshot); refreshes everything EkLink feeds. */
export function useRunSync() {
  const queryClient = useQueryClient();
  const { refreshUser } = useAuth();
  return useMutation<Awaited<ReturnType<typeof adminApi.runSync>>, ApiError, "changes" | "full">({
    mutationFn: (kind) => (kind === "full" ? adminApi.fullResync() : adminApi.runSync()),
    onSuccess: (outcome) => {
      queryClient.setQueryData(adminKeys.syncStatus(), outcome.status);
      void queryClient.invalidateQueries({ queryKey: adminKeys.all });
      void queryClient.invalidateQueries({ queryKey: templateKeys.accessOptions() });
      void refreshUser();
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: adminKeys.syncStatus() }),
  });
}

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
      void queryClient.invalidateQueries({ queryKey: adminKeys.instituteLists() });
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
    void queryClient.invalidateQueries({ queryKey: adminKeys.instituteLists() });
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
    mutationFn: (input: string | { name: string; code?: string | null }) =>
      typeof input === "string"
        ? adminApi.createOrganization(input)
        : adminApi.createOrganization(input.name, input.code),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateOrganization() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: DirectoryUpdate }) =>
      adminApi.updateOrganization(id, body),
    onSuccess: () => invalidate({ renamed: true }),
  });
}

export function useCreateInstitute() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({
      name,
      organizationId,
      code,
    }: {
      name: string;
      organizationId?: number;
      code?: string | null;
    }) => adminApi.createInstitute(name, organizationId, code),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateInstitute() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: DirectoryUpdate }) =>
      adminApi.updateInstitute(id, body),
    onSuccess: () => invalidate({ renamed: true }),
  });
}

export function useDeleteInstitute() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: (id: number) => adminApi.deleteInstitute(id),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateDepartment() {
  const invalidate = useInvalidateDirectory();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: DirectoryUpdate }) =>
      adminApi.updateDepartment(id, body),
    onSuccess: () => invalidate({ renamed: true }),
  });
}

export function useCreateApprover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApproverAssignmentCreate) => adminApi.createApprover(body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: adminKeys.approverLists() }),
  });
}

export function useEndApprover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => adminApi.endApprover(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: adminKeys.approverLists() }),
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
    mutationFn: ({
      name,
      organizationId,
      instituteId,
      code,
    }: {
      name: string;
      organizationId?: number;
      instituteId?: number;
      code?: string | null;
    }) => adminApi.createDepartment(name, organizationId, instituteId, code),
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
