import { useMemo, useState } from "react";
import { BadgeCheck, ExternalLink, Loader2, Plus, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { AdminQueryError } from "@/features/admin/AdminRoute";
import { ConfirmDialog } from "@/features/admin/ConfirmDialog";
import { FromEklinkBadge } from "@/features/admin/ManagedInEklink";
import {
  useAdminUsers,
  useApprovers,
  useCreateApprover,
  useDepartments,
  useEndApprover,
  useInstitutes,
  useOrganizations,
  useSyncStatus,
} from "@/hooks/queries";
import {
  canCreateApprovers,
  canEndApprover,
  departmentsOf,
  institutesOf,
} from "@/lib/admin-permissions";
import {
  ApiError,
  type AdminUser,
  type ApproverAssignment,
  type ApproverScopeLevel,
} from "@/lib/api";
import { formatRole } from "@/lib/format";

const SCOPE_LABEL: Record<ApproverScopeLevel, string> = {
  organization: "Organization",
  institute: "Institute",
  department: "Department",
};

/** Scope levels an admin may hand out (never wider than their own scope). */
function scopeLevelsFor(role: string): ApproverScopeLevel[] {
  if (role === "super_admin" || role === "org_admin") return ["organization", "institute", "department"];
  if (role === "institute_admin") return ["institute", "department"];
  return ["department"];
}

interface AssignDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titles: string[];
}

function AssignApproverDialog({ open, onOpenChange, titles }: AssignDialogProps) {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [person, setPerson] = useState<AdminUser | null>(null);
  const [title, setTitle] = useState(titles[0] ?? "HOD");
  const [level, setLevel] = useState<ApproverScopeLevel>("department");
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [instituteId, setInstituteId] = useState<number | null>(null);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [scopeKey, setScopeKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const createApprover = useCreateApprover();

  // Only active faculty and staff can be approvers.
  const people = useAdminUsers(
    {
      search: search.trim() || undefined,
      is_active: true,
      member_type: "faculty,staff",
      limit: 20,
    },
    open,
  );
  const candidates = people.data?.users ?? [];
  const organizations = useOrganizations(open);
  const institutes = useInstitutes(undefined, open);
  const departments = useDepartments(undefined, open);

  if (!user) return null;
  const levels = scopeLevelsFor(user.role);

  const choosePerson = (row: AdminUser) => {
    setPerson(row);
    setOrganizationId(row.organization_id);
    setInstituteId(row.institute_id ?? null);
    setDepartmentId(row.department_id);
  };

  const orgChoices = (organizations.data ?? []).filter(
    (org) => user.role === "super_admin" || org.id === user.organization_id,
  );
  const instChoices = institutesOf(institutes.data ?? [], organizationId);
  const deptChoices = departmentsOf(departments.data ?? [], organizationId, instituteId);

  const submit = async () => {
    if (!person) return setError("Choose a faculty or staff member");
    setError(null);
    try {
      await createApprover.mutateAsync({
        user_id: person.id,
        title,
        scope_level: level,
        organization_id: organizationId,
        institute_id: level === "organization" ? null : instituteId,
        department_id: level === "department" ? departmentId : null,
        scope_key: scopeKey.trim() || null,
      });
      onOpenChange(false);
      setPerson(null);
      setSearch("");
      setScopeKey("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not assign. Please try again.");
    }
  };

  const select = (
    label: string,
    value: number | null,
    onChange: (value: number | null) => void,
    choices: { id: number; name: string }[],
  ) => (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Select
        value={value !== null && choices.some((c) => c.id === value) ? String(value) : ""}
        onValueChange={(next) => onChange(next ? Number(next) : null)}
        disabled={choices.length === 0}
      >
        <SelectTrigger>
          <SelectValue placeholder={choices.length ? `Select ${label.toLowerCase()}` : "None available"} />
        </SelectTrigger>
        <SelectContent>
          {choices.map((choice) => (
            <SelectItem key={choice.id} value={String(choice.id)}>
              {choice.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !createApprover.isPending && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] overflow-y-auto sm:w-full">
        <DialogHeader>
          <DialogTitle>Assign an approver</DialogTitle>
          <DialogDescription>
            Approver is a job, not a role: the person keeps their role and gains this approval duty.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="approver-search">Faculty or staff member</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                id="approver-search"
                className="pl-9"
                placeholder="Search name, email or login ID"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <div className="max-h-40 overflow-y-auto rounded-md border border-slate-200">
              {people.isPending || people.isPlaceholderData ? (
                <p className="p-3 text-sm text-slate-500">Loading…</p>
              ) : candidates.length === 0 ? (
                <p className="p-3 text-sm text-slate-500">No faculty or staff match.</p>
              ) : (
                candidates.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => choosePerson(row)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                      person?.id === row.id ? "bg-slate-100" : ""
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{row.full_name}</span>
                      <span className="block truncate text-xs text-slate-500">
                        {[row.login_id, row.department ?? row.institute].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <Badge variant="secondary">{formatRole(row.member_type ?? row.role)}</Badge>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Job</Label>
              <Select value={title} onValueChange={setTitle}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {titles.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Applies to</Label>
              <Select value={level} onValueChange={(next) => setLevel(next as ApproverScopeLevel)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {levels.map((value) => (
                    <SelectItem key={value} value={value}>
                      {SCOPE_LABEL[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {user.role === "super_admin" &&
              select("Organization", organizationId, (id) => {
                setOrganizationId(id);
                setInstituteId(null);
                setDepartmentId(null);
              }, orgChoices)}
            {level !== "organization" &&
              select("Institute", instituteId, (id) => {
                setInstituteId(id);
                setDepartmentId(null);
              }, instChoices)}
            {level === "department" && select("Department", departmentId, setDepartmentId, deptChoices)}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="approver-key">Narrower scope (optional)</Label>
            <Input
              id="approver-key"
              maxLength={64}
              placeholder="e.g. 2024-28-A for a class, or hackathon"
              value={scopeKey}
              onChange={(event) => setScopeKey(event.target.value)}
            />
          </div>

          {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={createApprover.isPending}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={createApprover.isPending || !person}>
            {createApprover.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Assign
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AdminApproversPage() {
  const { user } = useAuth();
  const sync = useSyncStatus();
  const [showEnded, setShowEnded] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [ending, setEnding] = useState<ApproverAssignment | null>(null);
  const approvers = useApprovers(!showEnded);
  const endApprover = useEndApprover();
  const titles = useMemo(() => approvers.data?.titles ?? ["HOD", "Director"], [approvers.data]);
  const rows = approvers.data?.assignments ?? [];
  // While EkLink sync is on, approver jobs are assigned (and ended) in EkLink.
  const syncEnabled = Boolean(sync.data?.enabled) || approvers.data?.can_create === false;
  const mayCreate = canCreateApprovers(user?.role, syncEnabled);
  const eklinkApproversUrl = sync.data?.links.approvers ?? null;

  if (approvers.isError && !approvers.data) {
    return <AdminQueryError error={approvers.error} onRetry={() => void approvers.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold">Approvers</h1>
          <p className="mt-1 text-sm text-slate-600">
            Faculty and staff who approve requests in your scope (HOD, Director, class teacher,
            exam cell…). Ending an assignment keeps its history.
            {syncEnabled && " Approver jobs are managed in EkLink and copied here automatically."}
          </p>
        </div>
        {mayCreate ? (
          <Button onClick={() => setAssigning(true)}>
            <Plus className="h-4 w-4" /> Assign approver
          </Button>
        ) : (
          syncEnabled &&
          eklinkApproversUrl && (
            <Button variant="outline" asChild>
              <a href={eklinkApproversUrl} target="_blank" rel="noreferrer">
                Assign approvers in EkLink <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          )
        )}
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input
          type="checkbox"
          className="h-4 w-4 accent-slate-900"
          checked={showEnded}
          onChange={(event) => setShowEnded(event.target.checked)}
        />
        Show ended assignments too
      </label>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3">Person</th>
                <th scope="col" className="px-4 py-3">Job</th>
                <th scope="col" className="hidden px-4 py-3 md:table-cell">Scope</th>
                <th scope="col" className="hidden px-4 py-3 md:table-cell">Since</th>
                <th scope="col" className="hidden px-4 py-3 lg:table-cell">Source</th>
                <th scope="col" className="px-4 py-3 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {approvers.isPending && (
                <tr>
                  <td colSpan={6} className="px-4 py-4">
                    <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                  </td>
                </tr>
              )}
              {!approvers.isPending && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    <BadgeCheck className="mx-auto mb-2 h-6 w-6 text-slate-400" />
                    No approvers assigned yet.
                  </td>
                </tr>
              )}
              {rows.map((row) => (
                <tr key={row.id} className={row.is_current ? "align-top" : "align-top text-slate-400"}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{row.user_name}</p>
                    <p className="break-all text-xs text-slate-500">
                      {[row.user_login_id, row.user_email].filter(Boolean).join(" · ")}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="secondary">{row.title}</Badge>
                    {!row.is_current && (
                      <Badge variant="outline" className="ml-1">
                        Ended
                      </Badge>
                    )}
                  </td>
                  <td className="hidden px-4 py-3 text-slate-700 md:table-cell">
                    {SCOPE_LABEL[row.scope_level]}: {row.scope_name ?? "—"}
                    {row.scope_key && <span className="text-slate-500"> · {row.scope_key}</span>}
                  </td>
                  <td className="hidden px-4 py-3 text-slate-700 md:table-cell">
                    {row.valid_from}
                    {row.valid_to && ` → ${row.valid_to}`}
                  </td>
                  <td className="hidden px-4 py-3 lg:table-cell">
                    {row.managed_by_eklink ? (
                      <FromEklinkBadge />
                    ) : (
                      <Badge variant="outline">TemplateOS</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canEndApprover(user?.role, row) && (
                      <Button variant="outline" size="sm" onClick={() => setEnding(row)}>
                        End
                      </Button>
                    )}
                    {row.is_current && row.managed_by_eklink && (
                      <span className="text-xs text-slate-500" title="End this job in EkLink">
                        Managed in EkLink
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {mayCreate && (
        <AssignApproverDialog open={assigning} onOpenChange={setAssigning} titles={titles} />
      )}

      {ending && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setEnding(null)}
          title="End this assignment?"
          description={
            <>
              <span className="font-medium text-slate-900">{ending.user_name}</span> stops being{" "}
              {ending.title} from today. The record is kept.
            </>
          }
          confirmLabel="End assignment"
          onConfirm={async () => {
            await endApprover.mutateAsync(ending.id);
          }}
        />
      )}
    </div>
  );
}
