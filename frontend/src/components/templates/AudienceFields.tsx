import { useEffect, useId, useState } from "react";
import { Building, Globe, Lock, Users, UsersRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { templateAccessApi } from "@/lib/api";
import type {
  TemplateAccessOptions,
  TemplateAccessUpdate,
  TemplateAudience,
  TemplateVisibility,
} from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import { formatRole } from "@/lib/format";
import { cn } from "@/lib/utils";

// ── Model ──────────────────────────────────────────────────────────────

export interface AudienceValue {
  visibility: TemplateVisibility | "";
  scope_organization: string;
  scope_department: string;
  role_mode: "all" | "selected";
  allowed_roles: string[];
}

export type AudienceErrors = Partial<Record<keyof AudienceValue, string>>;

export const EMPTY_AUDIENCE: AudienceValue = {
  visibility: "",
  scope_organization: "",
  scope_department: "",
  role_mode: "all",
  allowed_roles: [],
};

interface VisibilityOption {
  value: TemplateVisibility;
  label: string;
  hint: string;
  icon: LucideIcon;
}

const VISIBILITY_OPTIONS: VisibilityOption[] = [
  { value: "private", label: "Private", hint: "Only you", icon: Lock },
  { value: "public", label: "Public", hint: "Everyone on TemplateOS", icon: Globe },
  {
    value: "organization",
    label: "Organization",
    hint: "Letterheads and organization-wide formats",
    icon: Building,
  },
  { value: "department", label: "Department", hint: "One department's formats", icon: Users },
  { value: "group", label: "Group", hint: "Users with the same role as you", icon: UsersRound },
];

const SCOPED: TemplateVisibility[] = ["organization", "department"];
const ROLE_RESTRICTABLE: TemplateVisibility[] = ["public", "organization", "department"];

export function isScoped(visibility: AudienceValue["visibility"]): boolean {
  return SCOPED.includes(visibility as TemplateVisibility);
}

export function supportsRoleRestriction(visibility: AudienceValue["visibility"]): boolean {
  return ROLE_RESTRICTABLE.includes(visibility as TemplateVisibility);
}

export function allowedVisibilities(
  options: TemplateAccessOptions | null,
): TemplateVisibility[] {
  return VISIBILITY_OPTIONS.map((option) => option.value).filter((value) => {
    if (value === "organization") return Boolean(options?.can_publish.organization);
    if (value === "department") return Boolean(options?.can_publish.department);
    return true;
  });
}

const same = (a: string | null | undefined, b: string | null | undefined) =>
  (a ?? "").trim().toLowerCase() === (b ?? "").trim().toLowerCase();

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
    if (!value.scope_organization.trim()) {
      errors.scope_organization =
        role === "super_admin"
          ? "Choose or enter an organization"
          : "Your profile has no organization. Add it on your profile first.";
    }
    if (value.visibility === "department" && !value.scope_department.trim()) {
      errors.scope_department =
        role === "department_admin"
          ? "Your profile has no department. Add it on your profile first."
          : "Choose or enter a department";
    }
    if (value.scope_organization.length > 255) errors.scope_organization = "Too long (max 255)";
    if (value.scope_department.length > 255) errors.scope_department = "Too long (max 255)";
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
    scope_organization: scoped ? value.scope_organization.trim() || null : null,
    scope_department:
      visibility === "department" ? value.scope_department.trim() || null : null,
    allowed_roles: restricted && value.allowed_roles.length ? value.allowed_roles : null,
  };
}

export function audienceFromTemplate(
  template: Pick<TemplateAudience, "scope_organization" | "scope_department" | "allowed_roles"> & {
    visibility: string;
  },
): AudienceValue {
  const roles = template.allowed_roles ?? [];
  return {
    visibility: template.visibility as TemplateVisibility,
    scope_organization: template.scope_organization ?? "",
    scope_department: template.scope_department ?? "",
    role_mode: roles.length ? "selected" : "all",
    allowed_roles: roles,
  };
}

/** Prefill scope from the user's defaults (and force it for org/dept admins). */
export function withScopeDefaults(
  value: AudienceValue,
  options: TemplateAccessOptions | null,
  role: string | undefined,
): AudienceValue {
  if (!isScoped(value.visibility) || !options) return value;
  const next = { ...value };
  const { defaults } = options;
  if (role === "org_admin" || role === "department_admin" || !next.scope_organization) {
    next.scope_organization = defaults.organization ?? next.scope_organization;
  }
  if (value.visibility === "department") {
    if (role === "department_admin" || !next.scope_department) {
      next.scope_department = defaults.department ?? next.scope_department;
    }
  } else {
    next.scope_department = "";
  }
  return next;
}

/** Load GET /templates/access-options once; null while loading or on failure. */
export function useAccessOptions(enabled = true) {
  const [options, setOptions] = useState<TemplateAccessOptions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    templateAccessApi
      .getOptions(getAccessToken())
      .then((data) => {
        if (!cancelled) setOptions(data);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Could not load audience options");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { options, error };
}

// ── Scope picker: pick a known value, or (when allowed) type a new one ─

const CUSTOM = "__custom__";

interface ScopePickerProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  choices: string[];
  allowCustom: boolean;
  locked: boolean;
  placeholder: string;
  error?: string;
  hint?: string;
}

function ScopePicker({
  id,
  label,
  value,
  onChange,
  choices,
  allowCustom,
  locked,
  placeholder,
  error,
  hint,
}: ScopePickerProps) {
  const inList = choices.some((choice) => same(choice, value));
  const [custom, setCustom] = useState(() => Boolean(value) && !inList);

  // A value set from outside (prefill, existing template) that is not in the
  // list must be shown in the text input, never as an orphan Select value.
  useEffect(() => {
    if (value && !inList && allowCustom) setCustom(true);
  }, [value, inList, allowCustom]);

  const errorId = `${id}-error`;
  const describedBy = error ? errorId : undefined;
  const showInput = locked || (allowCustom && (custom || choices.length === 0));
  // The Select must always receive a value that has a matching item.
  const selectValue = inList ? choices.find((choice) => same(choice, value)) ?? "" : "";

  return (
    <div className="min-w-0 space-y-2">
      <Label htmlFor={id} className={cn(error && "text-destructive")}>
        {label}
      </Label>
      {showInput ? (
        <div className="flex items-center gap-2">
          <Input
            id={id}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            maxLength={255}
            readOnly={locked}
            disabled={locked}
            aria-invalid={Boolean(error)}
            aria-describedby={describedBy}
            className="min-w-0"
          />
          {!locked && choices.length > 0 && (
            <button
              type="button"
              className="shrink-0 text-xs font-medium text-slate-600 underline-offset-2 hover:underline"
              onClick={() => {
                setCustom(false);
                onChange("");
              }}
            >
              Choose from list
            </button>
          )}
        </div>
      ) : (
        <Select
          value={selectValue}
          onValueChange={(next) => {
            if (next === CUSTOM) {
              setCustom(true);
              onChange("");
            } else {
              onChange(next);
            }
          }}
        >
          <SelectTrigger id={id} aria-invalid={Boolean(error)} aria-describedby={describedBy}>
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent>
            {choices.map((choice) => (
              <SelectItem key={choice} value={choice}>
                {choice}
              </SelectItem>
            ))}
            {allowCustom && <SelectItem value={CUSTOM}>Enter a new name…</SelectItem>}
          </SelectContent>
        </Select>
      )}
      {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      {error && (
        <p id={errorId} className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

// ── Audience editor ────────────────────────────────────────────────────

interface AudienceFieldsProps {
  value: AudienceValue;
  onChange: (value: AudienceValue) => void;
  options: TemplateAccessOptions | null;
  role: string | undefined;
  errors?: AudienceErrors;
  disabled?: boolean;
}

export function AudienceFields({
  value,
  onChange,
  options,
  role,
  errors = {},
  disabled = false,
}: AudienceFieldsProps) {
  const baseId = useId();
  const permitted = allowedVisibilities(options);
  const visibleOptions = VISIBILITY_OPTIONS.filter(
    // Keep the current value listed so the Select never holds an orphan value.
    (option) => permitted.includes(option.value) || option.value === value.visibility,
  );
  const isSuperAdmin = role === "super_admin";
  const orgLocked = role === "org_admin" || role === "department_admin";
  const deptLocked = role === "department_admin";

  const organizations = options?.organizations ?? [];
  const departments = Array.from(
    new Set(
      (options?.departments ?? [])
        .filter(
          (entry) =>
            !value.scope_organization.trim() ||
            !entry.organization ||
            same(entry.organization, value.scope_organization),
        )
        .map((entry) => entry.department),
    ),
  ).sort((a, b) => a.localeCompare(b));

  const setVisibility = (visibility: string) => {
    onChange(
      withScopeDefaults(
        { ...value, visibility: visibility as TemplateVisibility },
        options,
        role,
      ),
    );
  };

  const toggleRole = (roleValue: string, checked: boolean) => {
    const next = checked
      ? [...value.allowed_roles, roleValue]
      : value.allowed_roles.filter((item) => item !== roleValue);
    const order = (options?.roles ?? []).map((item) => item.value);
    next.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    onChange({ ...value, allowed_roles: next });
  };

  const visibilityId = `${baseId}-visibility`;
  const roleOptions = options?.roles ?? [];

  return (
    <fieldset className="min-w-0 space-y-4" disabled={disabled}>
      <div className="space-y-2">
        <Label htmlFor={visibilityId} className={cn(errors.visibility && "text-destructive")}>
          Visibility <span className="text-red-500">*</span>
        </Label>
        <Select value={value.visibility} onValueChange={setVisibility} disabled={disabled}>
          <SelectTrigger
            id={visibilityId}
            aria-invalid={Boolean(errors.visibility)}
            aria-describedby={errors.visibility ? `${visibilityId}-error` : undefined}
          >
            <SelectValue placeholder="Select visibility" />
          </SelectTrigger>
          <SelectContent>
            {visibleOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                <span className="flex items-center gap-2">
                  <option.icon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span>{option.label}</span>
                  <span className="hidden text-xs text-slate-500 sm:inline">— {option.hint}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.visibility ? (
          <p id={`${visibilityId}-error`} className="text-sm font-medium text-destructive">
            {errors.visibility}
          </p>
        ) : (
          options &&
          !options.can_publish.organization &&
          !options.can_publish.department && (
            <p className="text-xs text-slate-500">
              Organization and department publishing is available to administrators.
            </p>
          )
        )}
      </div>

      {isScoped(value.visibility) && (
        <div className="grid min-w-0 gap-4 sm:grid-cols-2">
          <ScopePicker
            id={`${baseId}-org`}
            label="Organization"
            value={value.scope_organization}
            onChange={(scope_organization) => onChange({ ...value, scope_organization })}
            choices={organizations}
            allowCustom={isSuperAdmin}
            locked={orgLocked}
            placeholder="Select an organization"
            error={errors.scope_organization}
            hint={orgLocked ? "Fixed to your own organization" : undefined}
          />
          {value.visibility === "department" && (
            <ScopePicker
              id={`${baseId}-dept`}
              label="Department"
              value={value.scope_department}
              onChange={(scope_department) => onChange({ ...value, scope_department })}
              choices={departments}
              allowCustom={!deptLocked}
              locked={deptLocked}
              placeholder="Select a department"
              error={errors.scope_department}
              hint={deptLocked ? "Fixed to your own department" : undefined}
            />
          )}
        </div>
      )}

      {supportsRoleRestriction(value.visibility) && (
        <div className="space-y-3 rounded-lg border border-slate-200 p-4">
          <div>
            <p className="text-sm font-medium">Who can use it</p>
            <p className="text-xs text-slate-500">
              {value.visibility === "public"
                ? "Everyone can see public templates unless you limit them to certain roles."
                : "Administrators of this scope can always see and manage it."}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:gap-6" role="radiogroup">
            {(
              [
                { mode: "all", label: "Everyone in scope" },
                { mode: "selected", label: "Only selected roles" },
              ] as const
            ).map((item) => (
              <label key={item.mode} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="radio"
                  name={`${baseId}-role-mode`}
                  className="h-4 w-4 accent-slate-900"
                  checked={value.role_mode === item.mode}
                  onChange={() => onChange({ ...value, role_mode: item.mode })}
                />
                {item.label}
              </label>
            ))}
          </div>
          {value.role_mode === "selected" && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {roleOptions.length === 0 && (
                <p className="text-sm text-slate-500">Loading roles…</p>
              )}
              {roleOptions.map((item) => (
                <label
                  key={item.value}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-0.5 text-sm hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-slate-900"
                    checked={value.allowed_roles.includes(item.value)}
                    onChange={(event) => toggleRole(item.value, event.target.checked)}
                  />
                  {item.label}
                </label>
              ))}
            </div>
          )}
          {errors.allowed_roles && (
            <p className="text-sm font-medium text-destructive">{errors.allowed_roles}</p>
          )}
        </div>
      )}
    </fieldset>
  );
}

/** Short human summary of a template's audience, for badges and detail rows. */
export function describeRoles(
  roles: string[] | null | undefined,
  options?: TemplateAccessOptions | null,
): string {
  if (!roles || roles.length === 0) return "Everyone in scope";
  const labels = new Map((options?.roles ?? []).map((item) => [item.value, item.label]));
  return roles.map((role) => labels.get(role) ?? formatRole(role)).join(", ");
}
