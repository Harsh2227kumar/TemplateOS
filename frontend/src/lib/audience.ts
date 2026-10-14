/**
 * Template audience model shared by the upload form and the Manage access
 * dialog: visibility, organization / department scope (by id, picked from
 * GET /templates/access-options) and the role restriction. Pure: only type
 * imports, so it runs under `node --test`.
 */
import type {
  DepartmentOption,
  TemplateAccessOptions,
  TemplateAccessUpdate,
  TemplateAudience,
  TemplateVisibility,
} from "@/lib/api/types";

export interface AudienceValue {
  visibility: TemplateVisibility | "";
  scope_organization_id: number | null;
  scope_department_id: number | null;
  role_mode: "all" | "selected";
  allowed_roles: string[];
}

export type AudienceErrors = Partial<Record<keyof AudienceValue, string>>;

export const EMPTY_AUDIENCE: AudienceValue = {
  visibility: "",
  scope_organization_id: null,
  scope_department_id: null,
  role_mode: "all",
  allowed_roles: [],
};

export const VISIBILITY_VALUES: TemplateVisibility[] = [
  "private",
  "public",
  "organization",
  "department",
  "group",
];
const SCOPED: TemplateVisibility[] = ["organization", "department"];
const ROLE_RESTRICTABLE: TemplateVisibility[] = ["public", "organization", "department"];

export function isScoped(visibility: AudienceValue["visibility"]): boolean {
  return SCOPED.includes(visibility as TemplateVisibility);
}

export function supportsRoleRestriction(visibility: AudienceValue["visibility"]): boolean {
  return ROLE_RESTRICTABLE.includes(visibility as TemplateVisibility);
}

export function allowedVisibilities(options: TemplateAccessOptions | null): TemplateVisibility[] {
  return VISIBILITY_VALUES.filter((value) => {
    if (value === "organization") return Boolean(options?.can_publish.organization);
    if (value === "department") return Boolean(options?.can_publish.department);
    return true;
  });
}

/** Departments of one organization, sorted by name. */
export function departmentChoices(
  options: TemplateAccessOptions | null,
  organizationId: number | null,
): DepartmentOption[] {
  if (!options || organizationId === null) return [];
  return options.departments
    .filter((department) => department.organization_id === organizationId)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Inline validation shared by the upload form and the Manage access dialog. */
export function validateAudience(
  value: AudienceValue,
  options: TemplateAccessOptions | null,
  role: string | undefined,
): AudienceErrors {
  const errors: AudienceErrors = {};
  if (!value.visibility) {
    errors.visibility = "Please select a visibility";
    return errors;
  }
  if (!allowedVisibilities(options).includes(value.visibility)) {
    errors.visibility = "You cannot publish templates with this visibility";
    return errors;
  }
  if (isScoped(value.visibility)) {
    if (value.scope_organization_id === null) {
      errors.scope_organization_id =
        role === "super_admin"
          ? "Choose an organization"
          : "Your profile has no organization. Ask an administrator to set it.";
    }
    if (value.visibility === "department") {
      if (value.scope_department_id === null) {
        errors.scope_department_id =
          role === "department_admin"
            ? "Your profile has no department. Ask an administrator to set it."
            : "Choose a department";
      } else if (
        options &&
        value.scope_organization_id !== null &&
        !departmentChoices(options, value.scope_organization_id).some(
          (department) => department.id === value.scope_department_id,
        )
      ) {
        errors.scope_department_id = "Choose a department of the selected organization";
      }
    }
  }
  if (
    supportsRoleRestriction(value.visibility) &&
    value.role_mode === "selected" &&
    value.allowed_roles.length === 0
  ) {
    errors.allowed_roles = "Select at least one role, or choose “Everyone in scope”";
  }
  return errors;
}

/** Normalize the editor state into what the API stores. */
export function toAccessPayload(value: AudienceValue): TemplateAccessUpdate {
  const visibility = value.visibility as TemplateVisibility;
  const scoped = isScoped(visibility);
  const restricted = supportsRoleRestriction(visibility) && value.role_mode === "selected";
  return {
    visibility,
    scope_organization_id: scoped ? value.scope_organization_id : null,
    scope_department_id: visibility === "department" ? value.scope_department_id : null,
    allowed_roles: restricted && value.allowed_roles.length ? value.allowed_roles : null,
  };
}

export function audienceFromTemplate(
  template: Pick<
    TemplateAudience,
    "scope_organization_id" | "scope_department_id" | "allowed_roles"
  > & { visibility: string },
): AudienceValue {
  const roles = template.allowed_roles ?? [];
  return {
    visibility: template.visibility as TemplateVisibility,
    scope_organization_id: template.scope_organization_id ?? null,
    scope_department_id: template.scope_department_id ?? null,
    role_mode: roles.length ? "selected" : "all",
    allowed_roles: roles,
  };
}

/**
 * Prefill the scope from the user's own organization / department, and force
 * it for org / department admins (the server does the same).
 */
export function withScopeDefaults(
  value: AudienceValue,
  options: TemplateAccessOptions | null,
  role: string | undefined,
): AudienceValue {
  if (!isScoped(value.visibility) || !options) return value;
  const next = { ...value };
  const { defaults } = options;
  if (role === "org_admin" || role === "department_admin" || next.scope_organization_id === null) {
    next.scope_organization_id = defaults.organization_id ?? next.scope_organization_id;
  }
  if (value.visibility === "department") {
    if (role === "department_admin" || next.scope_department_id === null) {
      next.scope_department_id = defaults.department_id ?? next.scope_department_id;
    }
    // Never keep a department of another organization.
    if (
      next.scope_department_id !== null &&
      !departmentChoices(options, next.scope_organization_id).some(
        (department) => department.id === next.scope_department_id,
      )
    ) {
      next.scope_department_id = null;
    }
  } else {
    next.scope_department_id = null;
  }
  return next;
}

/** Changing the organization drops a department that belongs to another one. */
export function withOrganization(
  value: AudienceValue,
  organizationId: number | null,
  options: TemplateAccessOptions | null,
): AudienceValue {
  const keepDepartment = departmentChoices(options, organizationId).some(
    (department) => department.id === value.scope_department_id,
  );
  return {
    ...value,
    scope_organization_id: organizationId,
    scope_department_id: keepDepartment ? value.scope_department_id : null,
  };
}

export function organizationName(
  options: TemplateAccessOptions | null,
  id: number | null,
): string | null {
  if (id === null) return null;
  return options?.organizations.find((organization) => organization.id === id)?.name ?? null;
}

export function departmentName(
  options: TemplateAccessOptions | null,
  id: number | null,
): string | null {
  if (id === null) return null;
  return options?.departments.find((department) => department.id === id)?.name ?? null;
}
