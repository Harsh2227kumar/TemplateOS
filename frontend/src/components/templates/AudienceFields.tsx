import { useId } from "react";
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
import { useTemplateAccessOptions } from "@/hooks/queries";
import type { TemplateAccessOptions, TemplateVisibility } from "@/lib/api";
import {
  allowedVisibilities,
  departmentChoices,
  departmentName,
  isScoped,
  organizationName,
  supportsRoleRestriction,
  withOrganization,
  withScopeDefaults,
  type AudienceErrors,
  type AudienceValue,
} from "@/lib/audience";
import { formatRole } from "@/lib/format";
import { cn } from "@/lib/utils";

// The model lives in @/lib/audience (pure, unit tested); re-exported so the
// existing imports from this module keep working.
export {
  EMPTY_AUDIENCE,
  allowedVisibilities,
  audienceFromTemplate,
  isScoped,
  supportsRoleRestriction,
  toAccessPayload,
  validateAudience,
  withScopeDefaults,
  type AudienceErrors,
  type AudienceValue,
} from "@/lib/audience";

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

/** GET /templates/access-options (cached); null while loading or on failure. */
export function useAccessOptions(enabled = true) {
  const query = useTemplateAccessOptions(enabled);
  const options: TemplateAccessOptions | null = query.data ?? null;
  const error =
    query.isError && !query.data
      ? query.error instanceof Error
        ? query.error.message
        : "Could not load audience options"
      : null;
  return { options, error };
}

// ── Scope picker: one row of the organizations / departments tables ────

interface ScopePickerProps {
  id: string;
  label: string;
  value: number | null;
  /** Name to show when the value is locked or not among the choices. */
  valueName: string | null;
  onChange: (value: number | null) => void;
  choices: { id: number; name: string }[];
  locked: boolean;
  placeholder: string;
  emptyHint: string;
  error?: string;
  hint?: string;
}

function ScopePicker({
  id,
  label,
  value,
  valueName,
  onChange,
  choices,
  locked,
  placeholder,
  emptyHint,
  error,
  hint,
}: ScopePickerProps) {
  const errorId = `${id}-error`;
  const describedBy = error ? errorId : undefined;
  const inList = value !== null && choices.some((choice) => choice.id === value);

  return (
    <div className="min-w-0 space-y-2">
      <Label htmlFor={id} className={cn(error && "text-destructive")}>
        {label}
      </Label>
      {locked ? (
        <Input
          id={id}
          value={valueName ?? ""}
          placeholder="Not set"
          readOnly
          disabled
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          className="min-w-0"
        />
      ) : (
        <Select
          // The Select must always receive a value that has a matching item.
          value={inList ? String(value) : ""}
          onValueChange={(next) => onChange(next ? Number(next) : null)}
          disabled={choices.length === 0}
        >
          <SelectTrigger id={id} aria-invalid={Boolean(error)} aria-describedby={describedBy}>
            <SelectValue placeholder={choices.length === 0 ? emptyHint : placeholder} />
          </SelectTrigger>
          <SelectContent>
            {choices.map((choice) => (
              <SelectItem key={choice.id} value={String(choice.id)}>
                {choice.name}
              </SelectItem>
            ))}
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
  const orgLocked = role === "org_admin" || role === "department_admin";
  const deptLocked = role === "department_admin";
  const organizations = options?.organizations ?? [];
  const departments = departmentChoices(options, value.scope_organization_id);

  const setVisibility = (visibility: string) => {
    onChange(
      withScopeDefaults({ ...value, visibility: visibility as TemplateVisibility }, options, role),
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
            value={value.scope_organization_id}
            valueName={organizationName(options, value.scope_organization_id)}
            onChange={(organizationId) =>
              onChange(withOrganization(value, organizationId, options))
            }
            choices={organizations}
            locked={orgLocked}
            placeholder="Select an organization"
            emptyHint="No organizations yet"
            error={errors.scope_organization_id}
            hint={
              orgLocked
                ? "Fixed to your own organization"
                : organizations.length === 0
                  ? "Create organizations under Admin → Organizations"
                  : undefined
            }
          />
          {value.visibility === "department" && (
            <ScopePicker
              id={`${baseId}-dept`}
              label="Department"
              value={value.scope_department_id}
              valueName={departmentName(options, value.scope_department_id)}
              onChange={(scope_department_id) => onChange({ ...value, scope_department_id })}
              choices={departments}
              locked={deptLocked}
              placeholder="Select a department"
              emptyHint={
                value.scope_organization_id === null
                  ? "Choose an organization first"
                  : "No departments in this organization"
              }
              error={errors.scope_department_id}
              hint={
                deptLocked
                  ? "Fixed to your own department"
                  : value.scope_organization_id !== null && departments.length === 0
                    ? "Create departments under Admin → Organizations"
                    : undefined
              }
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
