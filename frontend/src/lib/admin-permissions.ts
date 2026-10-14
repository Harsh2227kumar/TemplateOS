/**
 * Client mirror of the server's user-management rules
 * (backend app/services/user_admin.py). The server enforces every rule; this
 * module only decides what the UI offers, so the two must agree. Pure: no
 * runtime imports, so it runs under `node --test`.
 */
import type { AdminUserUpdate } from "@/lib/api/types";

export const USER_ROLES = [
  "super_admin",
  "org_admin",
  "department_admin",
  "faculty",
  "student",
  "approver",
  "normal_user",
] as const;

export type UserRole = (typeof USER_ROLES)[number];

export const USER_ADMIN_ROLES: readonly string[] = ["super_admin", "org_admin", "department_admin"];

const ASSIGNABLE: Record<string, readonly string[]> = {
  super_admin: USER_ROLES,
  org_admin: ["department_admin", "faculty", "student", "approver", "normal_user"],
  department_admin: ["faculty", "student", "approver", "normal_user"],
};

/** The membership fields the rules look at (a User or an AdminUser). */
export interface Member {
  id: number;
  role: string;
  organization_id: number | null;
  department_id: number | null;
}

export function isUserAdmin(role: string | null | undefined): boolean {
  return Boolean(role) && USER_ADMIN_ROLES.includes(role as string);
}

/** Roles `actorRole` may give to someone else. */
export function assignableRoles(actorRole: string | null | undefined): string[] {
  return [...(ASSIGNABLE[actorRole ?? ""] ?? [])];
}

/** Same scope rule as GET /admin/users. */
export function canSeeUser(actor: Member, target: Member): boolean {
  if (actor.role === "super_admin") return true;
  if (actor.id === target.id) return isUserAdmin(actor.role);
  if (actor.role === "org_admin") {
    return actor.organization_id !== null && target.organization_id === actor.organization_id;
  }
  if (actor.role === "department_admin") {
    return actor.department_id !== null && target.department_id === actor.department_id;
  }
  return false;
}

/** May the actor open the edit dialog for this user at all? */
export function canEditUser(actor: Member, target: Member): boolean {
  if (!isUserAdmin(actor.role) || !canSeeUser(actor, target)) return false;
  return actor.id === target.id || assignableRoles(actor.role).includes(target.role);
}

/** Nobody changes their own role. */
export function canChangeRole(actor: Member, target: Member): boolean {
  return actor.id !== target.id && canEditUser(actor, target);
}

/** Only a super admin moves users between organizations. */
export function canChangeOrganization(actor: Pick<Member, "role">): boolean {
  return actor.role === "super_admin";
}

/** super_admin anywhere, org_admin inside their organization; department admins never. */
export function canChangeDepartment(actor: Pick<Member, "role">): boolean {
  return actor.role === "super_admin" || actor.role === "org_admin";
}

/** Role choices for the edit dialog: what the actor may assign, plus the current role. */
export function roleChoices(actor: Member, target: Member): string[] {
  const allowed = canChangeRole(actor, target) ? assignableRoles(actor.role) : [];
  const choices = allowed.includes(target.role) ? allowed : [target.role, ...allowed];
  return USER_ROLES.filter((role) => choices.includes(role));
}

export function canManageOrganizations(role: string | null | undefined): boolean {
  return role === "super_admin";
}

/** Create / rename / delete departments of `organizationId`. */
export function canManageDepartments(
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

export function departmentsOf<T extends { organization_id: number }>(
  departments: readonly T[],
  organizationId: number | null,
): T[] {
  if (organizationId === null) return [];
  return departments.filter((department) => department.organization_id === organizationId);
}

export interface UserEditValues {
  role: string;
  organization_id: number | null;
  department_id: number | null;
}

export type UserEditErrors = Partial<Record<keyof UserEditValues, string>>;

/**
 * Client-side checks before PATCH /admin/users/{id} (the server repeats them).
 * `departmentOrg` maps a department id to its organization id.
 */
export function validateUserEdit(
  values: UserEditValues,
  departmentOrg: ReadonlyMap<number, number>,
): UserEditErrors {
  const errors: UserEditErrors = {};
  if (values.department_id !== null) {
    const org = departmentOrg.get(values.department_id);
    if (org === undefined || org !== values.organization_id) {
      errors.department_id = "Choose a department of the selected organization";
    }
  }
  if (values.role === "org_admin" && values.organization_id === null) {
    errors.organization_id = "An organization admin needs an organization";
  }
  if (values.role === "department_admin" && values.department_id === null) {
    errors.department_id = "A department admin needs a department";
  }
  return errors;
}

/** Only the fields that changed and that the actor may change. */
export function buildUserUpdate(
  actor: Member,
  target: Member,
  values: UserEditValues,
): AdminUserUpdate {
  const body: AdminUserUpdate = {};
  if (values.role !== target.role && canChangeRole(actor, target)) body.role = values.role;
  if (values.organization_id !== target.organization_id && canChangeOrganization(actor)) {
    body.organization_id = values.organization_id;
  }
  if (values.department_id !== target.department_id && canChangeDepartment(actor)) {
    body.department_id = values.department_id;
  }
  return body;
}
