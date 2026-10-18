import { lazy, Suspense, type ComponentProps } from "react";

import { Skeleton } from "@/components/ui/skeleton";

const VersionHistoryPanel = lazy(() =>
  import("./VersionHistoryPanel").then((module) => ({ default: module.VersionHistoryPanel })),
);

/** The version history, loaded on demand (keeps the main bundle small). */
export function LazyVersionHistoryPanel(props: ComponentProps<typeof VersionHistoryPanel>) {
  return (
    <Suspense fallback={<Skeleton className="h-32 bg-slate-100" aria-label="Loading versions" />}>
      <VersionHistoryPanel {...props} />
    </Suspense>
  );
}
