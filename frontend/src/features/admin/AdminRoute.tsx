import { Link, Outlet } from "react-router-dom";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { isUserAdmin } from "@/lib/admin-permissions";
import { errorStatus } from "@/lib/query/retry";

export function ForbiddenNotice({
  message = "This area is for administrators. Ask your department admin if you need access.",
}: {
  message?: string;
}) {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-amber-600">
        <ShieldAlert className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-slate-900">You do not have access</h2>
      <p className="mt-2 text-sm text-slate-600">{message}</p>
      <Button asChild variant="outline" className="mt-6">
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}

/**
 * Role guard for /admin/* (the server enforces the same rule; this only
 * avoids rendering pages the user cannot use).
 */
export function AdminRoute() {
  const { user } = useAuth();
  if (!isUserAdmin(user?.role)) return <ForbiddenNotice />;
  return <Outlet />;
}

/** Message for a failed admin query: a 403 (e.g. role changed meanwhile) gets the friendly notice. */
export function AdminQueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (errorStatus(error) === 403) {
    return (
      <ForbiddenNotice
        message={error instanceof Error ? error.message : "You do not have access to this list."}
      />
    );
  }
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <p>{error instanceof Error ? error.message : "Something went wrong."}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
