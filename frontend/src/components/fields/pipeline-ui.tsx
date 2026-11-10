import type { ReactNode } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Info, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { confidenceLevel } from "@/lib/template-pipeline";

/** `{{ key }}` chip used across the pipeline pages. */
export function MonoKey({ name, className = "" }: { name: string; className?: string }) {
  return (
    <code
      className={`inline-block max-w-full break-all rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700 ${className}`}
    >
      {`{{ ${name || "key"} }}`}
    </code>
  );
}

const CONFIDENCE_STYLES = {
  high: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-slate-200 bg-slate-50 text-slate-600",
} as const;

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const level = confidenceLevel(confidence);
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${CONFIDENCE_STYLES[level]}`}
      title={`Confidence ${Math.round(confidence * 100)}%`}
    >
      {level === "high" ? "High" : level === "medium" ? "Medium" : "Low"} ·{" "}
      {Math.round(confidence * 100)}%
    </span>
  );
}

const NOTICE_STYLES = {
  error: { box: "border-red-200 bg-red-50 text-red-700", Icon: XCircle },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-800", Icon: AlertTriangle },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-700", Icon: CheckCircle2 },
  info: { box: "border-slate-200 bg-slate-50 text-slate-600", Icon: Info },
} as const;

export function Notice({
  tone,
  title,
  children,
  action,
}: {
  tone: keyof typeof NOTICE_STYLES;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const { box, Icon } = NOTICE_STYLES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex flex-col gap-3 rounded-lg border p-3 text-sm sm:flex-row sm:items-start ${box}`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="break-words">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Full-page load error with consistent copy for 403/404. */
export function PipelineLoadError({
  status,
  message,
  onBack,
  onRetry,
}: {
  status?: number;
  message?: string;
  onBack: () => void;
  onRetry?: () => void;
}) {
  const title =
    status === 404
      ? "Template not found"
      : status === 403
        ? "You do not have access to this template"
        : "Something went wrong";
  return (
    <div className="mx-auto max-w-xl space-y-4 px-2 py-16 text-center">
      <h2 className="text-2xl font-semibold">{title}</h2>
      {status !== 404 && status !== 403 && message && (
        <p className="text-sm text-slate-600">{message}</p>
      )}
      <div className="flex flex-wrap justify-center gap-3 pt-2">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        {onRetry && status !== 404 && status !== 403 && (
          <Button onClick={onRetry}>Retry</Button>
        )}
      </div>
    </div>
  );
}

/** "Step n of 3" breadcrumb for the preparation pipeline. */
export function PipelineSteps({ current }: { current: 1 | 2 | 3 }) {
  const steps = ["Clean template", "Review placeholders", "Set up fields"];
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500" aria-label="Template setup steps">
      {steps.map((label, index) => {
        const number = index + 1;
        const active = number === current;
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold ${
                active ? "bg-slate-900 text-white" : number < current ? "bg-slate-300 text-slate-700" : "bg-slate-100 text-slate-500"
              }`}
            >
              {number}
            </span>
            <span className={active ? "font-medium text-slate-900" : undefined}>{label}</span>
            {number < steps.length && <span className="text-slate-300">/</span>}
          </li>
        );
      })}
    </ol>
  );
}
