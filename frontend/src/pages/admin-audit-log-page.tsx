import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { FileDown, Loader2, ScrollText, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { AdminQueryError, ForbiddenNotice } from "@/features/admin/AdminRoute";
import {
  AUDIT_PAGE_SIZE,
  ENTITY_TYPE_OPTIONS,
  actionLabel,
  actorLabel,
  auditFiltersToParams,
  auditFiltersToQuery,
  dateRangeError,
  entityLink,
  entityText,
  groupActions,
  queryToAuditFilters,
  type AuditFilters,
} from "@/features/admin/audit-model";
import { useAuditActions, useAuditLogs, useExportAuditCsv } from "@/hooks/queries";
import type { AuditActionOption, AuditLogItem } from "@/lib/api";
import { parseServerDate } from "@/lib/dates";
import { errorStatus } from "@/lib/query/retry";

const ALL = "all";
const FORBIDDEN = "You don't have access to the audit log.";

function When({ value }: { value: string }) {
  const date = parseServerDate(value);
  return (
    <span title={date ? `${date.toLocaleString()} (your time)` : undefined}>
      {date ? formatDistanceToNow(date, { addSuffix: true }) : ""}
    </span>
  );
}

function EntityCell({ item }: { item: AuditLogItem }) {
  const link = entityLink(item);
  const text = entityText(item);
  return link ? (
    <Link to={link} className="text-blue-700 hover:underline">
      {text}
    </Link>
  ) : (
    <span className="text-slate-600">{text}</span>
  );
}

function DetailsDialog({
  item,
  actions,
  onClose,
}: {
  item: AuditLogItem | null;
  actions: AuditActionOption[] | undefined;
  onClose: () => void;
}) {
  const date = item ? parseServerDate(item.created_at) : null;
  return (
    <Dialog open={item !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        {item && (
          <>
            <DialogHeader>
              <DialogTitle>{actionLabel(item.action, actions)}</DialogTitle>
              <DialogDescription>{item.summary}</DialogDescription>
            </DialogHeader>
            <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
              <dt className="text-slate-500">When</dt>
              <dd className="break-words">{date ? date.toLocaleString() : item.created_at} <span className="text-slate-400">(UTC {item.created_at.replace("T", " ").slice(0, 19)})</span></dd>
              <dt className="text-slate-500">Who</dt>
              <dd className="break-words">{actorLabel(item)}</dd>
              <dt className="text-slate-500">Action</dt>
              <dd className="font-mono text-xs leading-5">{item.action}</dd>
              <dt className="text-slate-500">Entity</dt>
              <dd><EntityCell item={item} /></dd>
              <dt className="text-slate-500">IP address</dt>
              <dd>{item.ip_address || "—"}</dd>
            </dl>
            <div className="space-y-1">
              <p className="text-sm text-slate-500">Details</p>
              <pre className="max-h-64 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-800">
                {item.details ? JSON.stringify(item.details, null, 2) : "—"}
              </pre>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** V1.7 P3: who did what, scoped by the server to the admin's organization / department. */
export function AdminAuditLogPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => queryToAuditFilters(searchParams), [searchParams]);
  const [searchInput, setSearchInput] = useState(filters.q);
  const [selected, setSelected] = useState<AuditLogItem | null>(null);
  const rangeError = dateRangeError(filters.from, filters.to);

  // Merged into the LATEST filters (a ref), so the debounced search, whose
  // timer holds an older render's closure, never undoes a filter changed meanwhile.
  const latestFilters = useRef(filters);
  latestFilters.current = filters;
  const setFilters = (next: Partial<AuditFilters>) => {
    const merged = { ...latestFilters.current, page: 1, ...next };
    latestFilters.current = merged;
    setSearchParams(auditFiltersToQuery(merged), { replace: true });
  };

  // Debounced free-text search (summary or email).
  useEffect(() => {
    if (searchInput.trim() === filters.q.trim()) return;
    const timer = window.setTimeout(() => setFilters({ q: searchInput }), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const actions = useAuditActions();
  const logs = useAuditLogs(auditFiltersToParams(filters), rangeError === null);
  const exportCsv = useExportAuditCsv();
  const groups = useMemo(() => groupActions(actions.data ?? []), [actions.data]);

  if (errorStatus(actions.error) === 403 || errorStatus(logs.error) === 403) {
    return <ForbiddenNotice message={FORBIDDEN} />;
  }

  const items = logs.data?.items ?? [];
  const total = logs.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / AUDIT_PAGE_SIZE));

  const handleExport = async () => {
    try {
      const filename = await exportCsv.mutateAsync(auditFiltersToParams(filters));
      toast({ title: "Audit log exported", description: filename, duration: 3000 });
    } catch (err) {
      toast({ variant: "destructive", title: "Export failed", description: err instanceof Error ? err.message : undefined });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Audit log</h1>
          <p className="mt-1 text-sm text-slate-600">Who did what, for the people and templates you administer.</p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleExport()}
          disabled={exportCsv.isPending || rangeError !== null}
          className="w-full sm:w-auto"
        >
          {exportCsv.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileDown className="h-4 w-4" aria-hidden="true" />}
          Export CSV
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="relative sm:col-span-2 lg:col-span-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search summary or email"
            aria-label="Search the audit log"
            className="pl-9"
            maxLength={200}
          />
        </div>
        <Select value={filters.action || ALL} onValueChange={(value) => setFilters({ action: value === ALL ? "" : value })}>
          <SelectTrigger aria-label="Filter by action">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All actions</SelectItem>
            {groups.map((group) => (
              <SelectGroup key={group.area}>
                <SelectLabel>{group.label}</SelectLabel>
                {group.actions.map((option) => (
                  <SelectItem key={option.action} value={option.action}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        <Select value={filters.entityType || ALL} onValueChange={(value) => setFilters({ entityType: value === ALL ? "" : value })}>
          <SelectTrigger aria-label="Filter by entity type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All entities</SelectItem>
            {ENTITY_TYPE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="space-y-1">
          <Label htmlFor="audit-from" className="text-xs text-slate-500">From (UTC)</Label>
          <Input id="audit-from" type="date" value={filters.from} max={filters.to || undefined}
                 onChange={(event) => setFilters({ from: event.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-to" className="text-xs text-slate-500">To (UTC)</Label>
          <Input id="audit-to" type="date" value={filters.to} min={filters.from || undefined}
                 onChange={(event) => setFilters({ to: event.target.value })} />
        </div>
      </div>

      {rangeError && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" role="alert">{rangeError}</p>
      )}

      {rangeError ? null : logs.isPending ? (
        <div className="space-y-2" aria-busy="true" aria-label="Loading the audit log">
          <Skeleton className="h-12 bg-slate-100" />
          <Skeleton className="h-12 bg-slate-100" />
          <Skeleton className="h-12 bg-slate-100" />
        </div>
      ) : logs.isError && !logs.data ? (
        <AdminQueryError error={logs.error} onRetry={() => void logs.refetch()} />
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-200 p-10 text-center">
          <ScrollText className="h-8 w-8 text-slate-300" aria-hidden="true" />
          <p className="mt-3 font-medium text-slate-700">No audit entries match these filters</p>
        </div>
      ) : (
        <>
          <ul className="space-y-3 sm:hidden" aria-label="Audit entries">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setSelected(item)}
                  className="w-full space-y-1 rounded-lg border border-slate-200 bg-white p-3 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  <p className="font-medium text-slate-900">{actionLabel(item.action, actions.data)}</p>
                  <p className="break-words text-slate-700">{item.summary}</p>
                  <p className="text-xs text-slate-500">
                    <When value={item.created_at} /> · {actorLabel(item)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm sm:block">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Time</th>
                    <th className="px-4 py-3">Actor</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Entity</th>
                    <th className="px-4 py-3">Summary</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((item) => (
                    <tr
                      key={item.id}
                      className="cursor-pointer hover:bg-slate-50"
                      onClick={() => setSelected(item)}
                    >
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600"><When value={item.created_at} /></td>
                      <td className="max-w-[12rem] truncate px-4 py-3" title={actorLabel(item)}>{actorLabel(item)}</td>
                      <td className="whitespace-nowrap px-4 py-3">{actionLabel(item.action, actions.data)}</td>
                      <td className="whitespace-nowrap px-4 py-3" onClick={(event) => event.stopPropagation()}>
                        <EntityCell item={item} />
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        <button
                          type="button"
                          className="text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelected(item);
                          }}
                        >
                          {item.summary}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Page {filters.page} of {pageCount} · {total} entr{total === 1 ? "y" : "ies"}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={filters.page <= 1}
                      onClick={() => setFilters({ page: filters.page - 1 })}>Previous</Button>
              <Button variant="outline" size="sm" disabled={filters.page >= pageCount}
                      onClick={() => setFilters({ page: filters.page + 1 })}>Next</Button>
            </div>
          </div>
        </>
      )}

      <DetailsDialog item={selected} actions={actions.data} onClose={() => setSelected(null)} />
    </div>
  );
}
