/**
 * Query-key factories. Every cache entry is created through these so keys are
 * stable and invalidation can target a whole subtree by prefix:
 *
 *   ["templates"]                                   everything template-related
 *   ["templates", "list"]                           my templates + library pages
 *   ["templates", "detail", id]                     one template and its children:
 *   ["templates", "detail", id, "fields"]
 *   ["templates", "detail", id, "content", source]
 *   ["templates", "detail", id, "clean-suggestions"]
 *   ["documents"]                                   every draft query
 *   ["documents", "detail", id, "versions", n]      a draft's versions (V1.7 P2)
 *
 * Kept free of runtime imports so it can be unit tested with `node --test`.
 */

export interface TemplateLibraryKeyParams {
  search?: string;
  category?: string;
  visibility?: string;
  status?: string;
  page?: number;
  limit?: number;
}

/** Drop empty filters so `{search: ""}` and `{}` share one cache entry. */
function compactParams<T extends object>(params: T): T {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") out[key] = value;
  }
  return out as T;
}

export const templateKeys = {
  all: ["templates"] as const,
  lists: () => [...templateKeys.all, "list"] as const,
  mine: () => [...templateKeys.lists(), "mine"] as const,
  library: (params: TemplateLibraryKeyParams = {}) =>
    [...templateKeys.lists(), "library", compactParams(params)] as const,
  accessOptions: () => [...templateKeys.all, "access-options"] as const,
  details: () => [...templateKeys.all, "detail"] as const,
  detail: (id: number) => [...templateKeys.details(), id] as const,
  fields: (id: number) => [...templateKeys.detail(id), "fields"] as const,
  content: (id: number, source: "original" | "processed" = "original") =>
    [...templateKeys.detail(id), "content", source] as const,
  cleanSuggestions: (id: number) => [...templateKeys.detail(id), "clean-suggestions"] as const,
};

export const documentKeys = {
  all: ["documents"] as const,
  lists: () => [...documentKeys.all, "list"] as const,
  mine: () => [...documentKeys.lists(), "mine"] as const,
  details: () => [...documentKeys.all, "detail"] as const,
  detail: (id: number) => [...documentKeys.details(), id] as const,
  /** Under detail(id), so every detail invalidation refreshes the preview too. */
  preview: (id: number) => [...documentKeys.detail(id), "preview"] as const,
  /** V1.7 P2: under detail(id): generate / restore / save refresh them. */
  versions: (id: number) => [...documentKeys.detail(id), "versions"] as const,
  version: (id: number, version: number) => [...documentKeys.versions(id), version] as const,
};

export interface AdminUserListKeyParams {
  search?: string;
  role?: string;
  organization_id?: number;
  department_id?: number;
  page?: number;
  limit?: number;
}

/**
 *   ["admin", "users"]                            every user-list page
 *   ["admin", "users", {filters}]                 one page
 *   ["admin", "organizations"]
 *   ["admin", "departments"]                      every department list
 *   ["admin", "departments", {organization_id}]
 */
export const adminKeys = {
  all: ["admin"] as const,
  users: () => [...adminKeys.all, "users"] as const,
  userList: (params: AdminUserListKeyParams = {}) =>
    [...adminKeys.users(), compactParams(params)] as const,
  organizations: () => [...adminKeys.all, "organizations"] as const,
  departmentLists: () => [...adminKeys.all, "departments"] as const,
  departments: (organizationId?: number) =>
    [
      ...adminKeys.departmentLists(),
      organizationId === undefined ? {} : { organization_id: organizationId },
    ] as const,
};

export const queryKeys = {
  templates: templateKeys,
  documents: documentKeys,
  admin: adminKeys,
};

/** True when `key` starts with `prefix` (how TanStack matches invalidations). */
export function keyStartsWith(key: readonly unknown[], prefix: readonly unknown[]): boolean {
  if (prefix.length > key.length) return false;
  return prefix.every((part, index) => JSON.stringify(part) === JSON.stringify(key[index]));
}
