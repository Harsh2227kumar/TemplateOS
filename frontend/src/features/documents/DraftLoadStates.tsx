import { Link } from "react-router-dom";
import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export function DraftLoadingSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-6" aria-busy="true">
      <div className="h-8 animate-pulse rounded bg-slate-100" />
      <div className="h-64 animate-pulse rounded bg-slate-100" />
    </div>
  );
}

interface DraftLoadErrorProps {
  title: string;
  message: string;
  onRetry: () => void;
  backTo: string;
  backLabel: string;
}

/** Retryable load failure (network, 5xx). */
export function DraftLoadError({ title, message, onRetry, backTo, backLabel }: DraftLoadErrorProps) {
  return (
    <div className="mx-auto max-w-3xl py-12 text-center">
      <AlertCircle className="mx-auto mb-4 h-12 w-12 text-red-400" />
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mt-2 text-slate-500">{message}</p>
      <div className="mt-6 flex justify-center gap-3">
        <Button onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Retry
        </Button>
        <Button asChild variant="outline">
          <Link to={backTo}>{backLabel}</Link>
        </Button>
      </div>
    </div>
  );
}

interface DraftNotFoundProps {
  title: string;
  description: string;
  backTo: string;
  backLabel: string;
}

/** 404 / 403: nothing to retry. */
export function DraftNotFound({ title, description, backTo, backLabel }: DraftNotFoundProps) {
  return (
    <div className="mx-auto max-w-3xl py-12 text-center">
      <AlertCircle className="mx-auto mb-4 h-12 w-12 text-slate-400" />
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mt-2 text-slate-500">{description}</p>
      <Button asChild className="mt-6">
        <Link to={backTo}>{backLabel}</Link>
      </Button>
    </div>
  );
}
