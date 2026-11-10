import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Minimal toast notifications (shadcn-style `toast()` / `useToast()` API)
 * without an extra Radix dependency. Mount <Toaster /> once near the root.
 */

export type ToastVariant = "default" | "destructive";

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  /** Auto-dismiss delay in ms (default 5000). */
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
}

let toasts: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<(items: ToastItem[]) => void>();

function emit() {
  for (const listener of listeners) listener(toasts);
}

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

const timers = new Map<number, number>();

export function toast(options: ToastOptions): number {
  // An identical toast already on screen (e.g. "AI is unavailable" from two
  // fields) is moved to the end and its timer restarted, not stacked.
  const duplicate = toasts.find(
    (t) => t.title === options.title && t.description === options.description && t.variant === options.variant,
  );
  const id = duplicate ? duplicate.id : nextId++;
  // Keep at most 3 on screen; the newest goes last.
  toasts = [...toasts.filter((t) => t.id !== id), { ...options, id }].slice(-3);
  emit();
  const existing = timers.get(id);
  if (existing !== undefined) window.clearTimeout(existing);
  timers.set(
    id,
    window.setTimeout(() => {
      timers.delete(id);
      dismissToast(id);
    }, options.duration ?? 5000),
  );
  return id;
}

export function useToast() {
  return { toast, dismiss: dismissToast };
}

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(toasts);

  useEffect(() => {
    listeners.add(setItems);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col gap-2 px-4 sm:left-auto sm:right-4 sm:w-full sm:max-w-sm sm:px-0"
    >
      {items.map((item) => {
        const destructive = item.variant === "destructive";
        return (
          <div
            key={item.id}
            role={destructive ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-md border p-4 shadow-lg",
              destructive
                ? "border-red-200 bg-red-50 text-red-900"
                : "border-slate-200 bg-white text-slate-900",
            )}
          >
            {destructive ? (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{item.title}</p>
              {item.description && (
                <p className={cn("mt-1 text-sm break-words", destructive ? "text-red-700" : "text-slate-600")}>
                  {item.description}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => dismissToast(item.id)}
              className="shrink-0 rounded p-0.5 opacity-70 hover:opacity-100"
              aria-label="Dismiss notification"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
