import { ExternalLink, Loader2, RefreshCw, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { useAuth } from "@/context/auth-context";
import { AdminQueryError } from "@/features/admin/AdminRoute";
import { useRunSync, useSyncStatus } from "@/hooks/queries";
import { canRunSync } from "@/lib/admin-permissions";
import { ApiError, type SyncStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Server timestamps are naive UTC. */
function formatTime(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const RESULT_LABELS: Record<string, string> = {
  applied: "Applied",
  created: "Created",
  adopted: "Linked to existing",
  deactivated: "Deactivated",
  reactivated: "Reactivated",
  unresolved: "Waiting for codes",
  skipped: "Skipped",
  conflict: "Conflicts",
  already_applied: "Already applied",
  name_conflicts: "Name conflicts",
  resolved_later: "Resolved from earlier",
  pending: "Still waiting",
  events: "Events received",
  pages: "Pages pulled",
  directory_applied: "Directory entries",
  person_applied: "People",
  approver_applied: "Approver jobs",
  person_unresolved: "People waiting for codes",
  approver_unresolved: "Jobs waiting for codes",
  linked_users_not_in_eklink: "Linked users missing in EkLink",
  eklink_jobs_not_in_snapshot: "EkLink jobs missing in snapshot",
};

function resultEntries(result: Record<string, unknown> | null): [string, number][] {
  if (!result) return [];
  return Object.entries(result)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .sort(([a], [b]) => a.localeCompare(b));
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <dt className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function StateBadge({ status }: { status: SyncStatus }) {
  if (!status.configured) {
    return <Badge variant="outline" className="border-slate-200 text-slate-600">Not configured</Badge>;
  }
  if (!status.enabled) {
    return <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">Switched off</Badge>;
  }
  if (status.last_error) {
    return <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">Last run failed</Badge>;
  }
  return <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">On</Badge>;
}

export function AdminSyncPage() {
  const { user } = useAuth();
  const status = useSyncStatus();
  const runSync = useRunSync();

  if (status.isError && !status.data) {
    return <AdminQueryError error={status.error} onRetry={() => void status.refetch()} />;
  }
  const data = status.data;
  const mayRun = canRunSync(user?.role) && Boolean(data?.can_run);
  const running = runSync.isPending ? runSync.variables : null;

  const run = async (kind: "changes" | "full") => {
    try {
      const outcome = await runSync.mutateAsync(kind);
      toast({
        title: kind === "full" ? "Full resync finished" : "Sync finished",
        description: `Up to EkLink change ${outcome.last_event_id}.`,
      });
    } catch (caught) {
      toast({
        variant: "destructive",
        title: kind === "full" ? "Full resync failed" : "Sync failed",
        description: caught instanceof ApiError ? caught.message : "Please try again.",
      });
    }
  };

  const entries = resultEntries(data?.last_result ?? null);
  const source = typeof data?.last_result?.source === "string" ? data.last_result.source : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            EkLink sync {data && <StateBadge status={data} />}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            EkLink owns people, their placement and approver jobs. Changes arrive instantly from
            EkLink; TemplateOS also checks every {data?.interval_minutes ?? 15} minutes and runs a
            full resync daily at {data?.full_at ?? "02:00"}. Templates and documents are never touched.
          </p>
          {data?.eklink_admin_url && (
            <a
              href={data.eklink_admin_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-sky-700 hover:underline"
            >
              Open the EkLink Admin Console <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
        </div>
        {mayRun && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void run("changes")} disabled={runSync.isPending}>
              {running === "changes" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Sync now
            </Button>
            <Button variant="outline" onClick={() => void run("full")} disabled={runSync.isPending}>
              {running === "full" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              Full resync
            </Button>
          </div>
        )}
      </div>

      {status.isPending || !data ? (
        <div className="space-y-2">
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
        </div>
      ) : (
        <>
          {!data.configured && (
            <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
              Sync starts once EKLINK_URL, EKLINK_CLIENT_ID and EKLINK_CLIENT_SECRET are set on the
              server.
            </p>
          )}
          {!mayRun && data.configured && (
            <p className="text-sm text-slate-500">Only a super admin can run the sync by hand.</p>
          )}

          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Fact label="Last change applied" value={`#${data.last_event_id}`} />
            <Fact label="Last pull" value={formatTime(data.last_pull_at)} />
            <Fact label="Last push from EkLink" value={formatTime(data.last_push_at)} />
            <Fact label="Last full resync" value={formatTime(data.last_full_sync_at)} />
          </dl>

          {data.last_error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <p className="font-medium">Last error</p>
              <p className="mt-1 break-words">{data.last_error}</p>
              <p className="mt-1 text-xs text-red-700">{formatTime(data.last_error_at)}</p>
            </div>
          )}

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
              <h2 className="text-sm font-semibold">Last result</h2>
              {source && <Badge variant="secondary">{source}</Badge>}
            </div>
            {entries.length === 0 ? (
              <p className="p-6 text-center text-sm text-slate-500">Nothing has been synced yet.</p>
            ) : (
              <dl className="grid gap-x-6 gap-y-2 p-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {entries.map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-2 border-b border-slate-100 py-1">
                    <dt className="text-slate-600">{RESULT_LABELS[key] ?? key.replace(/_/g, " ")}</dt>
                    <dd className={cn("font-mono", value > 0 ? "text-slate-900" : "text-slate-400")}>{value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {data.pending_count > 0 && (
              <p className="border-t border-slate-200 px-4 py-3 text-xs text-slate-500">
                {data.pending_count} change{data.pending_count === 1 ? "" : "s"} wait for an
                organization, institute, department or person TemplateOS does not know yet. They are
                retried with every sync; a full resync settles them.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
