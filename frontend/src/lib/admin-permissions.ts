/**
 * Client mirror of the server's user-management rules
 * (backend app/services/user_admin.py and app/services/scopes.py). The
 * server enforces every rule; this module only decides what the UI offers,
 * so the two must agree. Pure: no runtime imports, so it runs under
 * `node --test`.
 *
 *   super_admin  >  org_admin  >  institute_admin  >  department_admin  >  faculty / staff / student
 *
 * "Approver" is not a role: faculty and staff hold approver assignments.
 * approver / normal_user are legacy roles: still shown for old accounts,
 * never offered.
 *
 * EkLink ownership (SYNC_CONTRACT.md section 7, server: user_admin.py and
 * admin.py): for EkLink-linked users (`managed_by_eklink`) organization,
 * institute, department, member type and the active flag are read-only;
 * their role may only become a TemplateOS admin role or their member type.
 * Directory rows with a code and approver jobs with source "eklink" are
 * read-only; new approver jobs are assigned in EkLink while sync is on.
 */
import type { AdminUserUpdate } from "@/lib/api/types";

export const USER_ROLES = [
  "super_admin",
  "org_admin",
  "institute_admin",
  "department_admin",
  "faculty",
  "staff",
  "student",
] as const;

export type UserRole = (typeof USER_ROLES)[number];

export const LEGACY_ROLES: readonly string[] = ["approver", "normal_user"];
export const MEMBER_TYPES = ["faculty", "staff", "student"] as const;

export const USER_ADMIN_ROLES: readonly string[] = [
  "super_admin",
  "org_admin",
  "institute_admin",
  "department_admin",
];

const ASSIGNABLE: Record<string, readonly string[]> = {
  super_admin: USER_ROLES,
  org_admin: ["institute_admin", "department_admin", "faculty", "staff", "student"],
  institute_admin: ["department_admin", "faculty", "staff", "student"],
  department_admin: ["faculty", "staff", "student"],
};

/** The membership fields the rules look at (a User or an AdminUser). */
export interface Member {
  id: number;
  role: string;
  organization_id: number | null;
  institute_id?: number | null;
  department_id: number | null;
  member_type?: string | null;
  /** Linked to EkLink: placement, member type and the active flag come from there. */
  managed_by_eklink?: boolean;
}

export const MANAGED_IN_EKLINK = "Managed in EkLink";

/** Anything the API marks as mirrored from EkLink (user, directory row, approver job). */
export function isEklinkManaged(row: { managed_by_eklink?: boolean } | null | undefined): boolean {
  return Boolean(row?.managed_by_eklink);
}

/** EkLink Admin Console page for a person (the base URL comes from /admin/sync/status). */
export function eklinkUserUrl(
  eklinkUrl: string | null | undefined,
  loginId: string | null | undefined,
): string | null {
  if (!eklinkUrl) return null;
  const base = eklinkUrl.replace(/\/+$/, "");
  return loginId
    ? `${base}/admin/users?login_id=${encodeURIComponent(loginId)}`
    : `${base}/admin/users`;
}

/** EkLink Admin Console page by section ("directory", "approvers", ...). */
export function eklinkAdminUrl(eklinkUrl: string | null | undefined, section: string): string | null {
  if (!eklinkUrl) return null;
  return `${eklinkUrl.replace(/\/+$/, "")}/admin/${section}`;
}

export function isUserAdmin(role: string | null | undefined): boolean {
  return Boolean(role) && USER_ADMIN_ROLES.includes(role as string);
}

/** Roles `actorRole` may give to someone else. */
export function assignableRoles(actorRole: string | null | undefined): string[] {
  return [...(ASSIGNABLE[actorRole ?? ""] ?? [])];
}

/** Can the actor modify someone holding `role` (legacy roles rank as members)? */
function canModifyRole(actorRole: string, role: string): boolean {
  const allowed = assignableRoles(actorRole);
  if (LEGACY_ROLES.includes(role)) return allowed.includes("staff");
  return allowed.includes(role);
}

/** Same scope rule as GET /admin/users. */
export function canSeeUser(actor: Member, target: Member): boolean {
  if (actor.role === "super_admin") return true;
  if (actor.id === target.id) return isUserAdmin(actor.role);
  if (actor.role === "org_admin") {
    return actor.organization_id !== null && target.organization_id === actor.organization_id;
  }
  if (actor.role === "institute_admin") {
    return (
      actor.institute_id != null && target.institute_id != null &&
      target.institute_id === actor.institute_id
    );
  }
  if (actor.role === "department_admin") {
    return actor.department_id !== null && target.department_id === actor.department_id;
  }
  return false;
}

/** May the actor open the edit dialog for this user at all? */
export function canEditUser(actor: Member, target: Member): boolean {
  if (!isUserAdmin(actor.role) || !canSeeUser(actor, target)) return false;
  return actor.id === target.id || canModifyRole(actor.role, target.role);
}

/** Nobody changes their own role. */
export function canChangeRole(actor: Member, target: Member): boolean {
  return actor.id !== target.id && canEditUser(actor, target);
}

/** Nobody deactivates themselves; EkLink-linked users are (de)activated in EkLink. */
export function canChangeActive(actor: Member, target: Member): boolean {
  return actor.id !== target.id && canEditUser(actor, target) && !isEklinkManaged(target);
}

/** Organization / institute / department / member type of this user may be edited here. */
export function canChangePlacement(target: Pick<Member, "managed_by_eklink">): boolean {
  return !isEklinkManaged(target);
}

/** The member type of an admin may be set here (not for EkLink-linked users, not for oneself). */
export function canChangeMemberType(actor: Member, target: Member): boolean {
  return actor.id !== target.id && canEditUser(actor, target) && !isEklinkManaged(target);
}

/** Only a super admin moves users between organizations. */
export function canChangeOrganization(actor: Pick<Member, "role">): boolean {
  return actor.role === "super_admin";
}

/** super_admin anywhere, org_admin inside their organization. */
export function canChangeInstitute(actor: Pick<Member, "role">): boolean {
  return actor.role === "super_admin" || actor.role === "org_admin";
}

/** super_admin, org_admin and institute_admin (inside their scope); department admins never. */
export function canChangeDepartment(actor: Pick<Member, "role">): boolean {
  return (
    actor.role === "super_admin" || actor.role === "org_admin" || actor.role === "institute_admin"
  );
}

/**
 * Role choices for the edit dialog: what the actor may assign, plus the
 * current role. EkLink-linked users: admin roles, or back to their EkLink
 * member type (member roles come from EkLink).
 */
export function roleChoices(actor: Member, target: Member): string[] {
  let allowed = canChangeRole(actor, target) ? assignableRoles(actor.role) : [];
  if (isEklinkManaged(target)) {
    allowed = allowed.filter(
      (role) => USER_ADMIN_ROLES.includes(role) || role === (target.member_type ?? null),
    );
  }
  const ordered: string[] = USER_ROLES.filter((role) => allowed.includes(role));
  if (!ordered.includes(target.role)) ordered.unshift(target.role);
  return ordered;
}

export function canManageOrganizations(role: string | null | undefined): boolean {
  return role === "super_admin";
}

/** Create / rename / deactivate institutes of `organizationId`. */
export function canManageInstitutes(
  actor: Pick<Member, "role" | "organization_id">,
  organizationId: number | null,
): boolean {
  if (actor.role === "super_admin") return true;
  return (
    actor.role === "org_admin" &&
    actor.organization_id !== null &&
    actor.organization_id === organizationId
  );
}

/** Create / rename / deactivate departments of an institute (or organization). */
export function canManageDepartments(
  actor: Pick<Member, "role" | "organization_id"> & { institute_id?: number | null },
  organizationId: number | null,
  instituteId?: number | null,
): boolean {
  if (actor.role === "super_admin") return true;
  if (actor.role === "org_admin") {
    return actor.organization_id !== null && actor.organization_id === organizationId;
  }
  if (actor.role === "institute_admin") {
    return (
      actor.institute_id != null &&
      (instituteId === undefined || instituteId === actor.institute_id)
    );
  }
  return false;
}

/** Manage approver assignments (any admin, inside their scope). */
export function canManageApprovers(role: string | null | undefined): boolean {
  return isUserAdmin(role);
}

/** New approver jobs are assigned in EkLink while the sync is on. */
export function canCreateApprovers(
  role: string | null | undefined,
  syncEnabled: boolean | null | undefined,
): boolean {
  return canManageApprovers(role) && !syncEnabled;
}

/** End a current local job (EkLink jobs are ended in EkLink). */
export function canEndApprover(
  role: string | null | undefined,
  assignment: { is_current: boolean; managed_by_eklink?: boolean },
): boolean {
  return canManageApprovers(role) && assignment.is_current && !isEklinkManaged(assignment);
}

/** Rename / toggle / delete a directory row: only local rows (no EkLink code). */
export function canEditDirectoryRow(row: { managed_by_eklink?: boolean } | null | undefined): boolean {
  return !isEklinkManaged(row);
}

/** Create institutes / departments under this parent: not under EkLink rows. */
export function canCreateUnder(parent: { managed_by_eklink?: boolean } | null | undefined): boolean {
  return !isEklinkManaged(parent);
}

/** Any admin may look at the sync status; only a super admin runs it. */
export function canViewSync(role: string | null | undefined): boolean {
  return isUserAdmin(role);
}

export function canRunSync(role: string | null | undefined): boolean {
  return role === "super_admin";
}

export function departmentsOf<T extends { organization_id: number; institute_id?: number | null }>(
  departments: readonly T[],
  organizationId: number | null,
  instituteId?: number | null,
): T[] {
  if (organizationId === null) return [];
  return departments.filter(
    (department) =>
      department.organization_id === organizationId &&
      (instituteId == null || department.institute_id === instituteId),
  );
}

export function institutesOf<T extends { organization_id: number }>(
  institutes: readonly T[],
  organizationId: number | null,
): T[] {
  if (organizationId === null) return [];
  return institutes.filter((institute) => institute.organization_id === organizationId);
}

export interface UserEditValues {
  role: string;
  organization_id: number | null;
  institute_id?: number | null;
  department_id: number | null;
  member_type?: string | null;
  is_active?: boolean;
}

export type UserEditErrors = Partial<Record<keyof UserEditValues, string>>;

/**
 * Client-side checks before PATCH /admin/users/{id} (the server repeats them).
 * `departmentOrg` maps a department id to its organization id;
 * `departmentInstitute` (optional) maps it to its institute id.
 */
export function validateUserEdit(
  values: UserEditValues,
  departmentOrg: ReadonlyMap<number, number>,
  departmentInstitute?: ReadonlyMap<number, number | null>,
): UserEditErrors {
  const errors: UserEditErrors = {};
  if (values.department_id !== null) {
    const org = departmentOrg.get(values.department_id);
    if (org === undefined || org !== values.organization_id) {
      errors.department_id = "Choose a department of the selected organization";
    } else if (departmentInstitute && values.institute_id != null) {
      const institute = departmentInstitute.get(values.department_id);
      if (institute != null && institute !== values.institute_id) {
        errors.department_id = "Choose a department of the selected institute";
      }
    }
  }
  if (values.role === "org_admin" && values.organization_id === null) {
    errors.organization_id = "An organization admin needs an organization";
  }
  if (
    values.role === "institute_admin" &&
    values.institute_id == null &&
    values.department_id === null
  ) {
    errors.institute_id = "An institute admin needs an institute";
  }
  if (values.role === "department_admin" && values.department_id === null) {
    errors.department_id = "A department admin needs a department";
  }
  return errors;
}

/**
 * Only the fields that changed and that the actor may change. For
 * EkLink-linked users the EkLink-owned fields are never sent.
 */
export function buildUserUpdate(
  actor: Member,
  target: Member & { member_type?: string | null; is_active?: boolean },
  values: UserEditValues,
): AdminUserUpdate {
  const body: AdminUserUpdate = {};
  if (
    values.role !== target.role &&
    canChangeRole(actor, target) &&
    roleChoices(actor, target).includes(values.role)
  ) {
    body.role = values.role;
  }
  if (isEklinkManaged(target)) return body;
  if (values.organization_id !== target.organization_id && canChangeOrganization(actor)) {
    body.organization_id = values.organization_id;
  }
  if (
    values.institute_id !== undefined &&
    values.institute_id !== (target.institute_id ?? null) &&
    canChangeInstitute(actor)
  ) {
    body.institute_id = values.institute_id;
  }
  if (values.department_id !== target.department_id && canChangeDepartment(actor)) {
    body.department_id = values.department_id;
  }
  if (
    values.member_type !== undefined &&
    values.member_type !== (target.member_type ?? null) &&
    !MEMBER_TYPES.includes((values.role ?? "") as (typeof MEMBER_TYPES)[number]) &&
    canEditUser(actor, target)
  ) {
    body.member_type = values.member_type;
  }
  if (
    values.is_active !== undefined &&
    values.is_active !== (target.is_active ?? true) &&
    canChangeActive(actor, target)
  ) {
    body.is_active = values.is_active;
  }
  return body;
}
