import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { MANAGED_IN_EKLINK } from "@/lib/admin-permissions";
import { cn } from "@/lib/utils";

/** "Managed in EkLink" hint under a read-only field, linking to EkLink's Admin Console. */
export function ManagedInEklink({
  href,
  className,
  children,
}: {
  href?: string | null;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <p className={cn("text-xs text-slate-500", className)}>
      {children ?? MANAGED_IN_EKLINK}
      {href && (
        <>
          {" · "}
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-0.5 font-medium text-sky-700 hover:underline"
          >
            Open in EkLink
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        </>
      )}
    </p>
  );
}

/** Small badge for rows mirrored from EkLink. */
export function FromEklinkBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("border-sky-200 bg-sky-50 text-sky-700", className)}
      title={MANAGED_IN_EKLINK}
    >
      From EkLink
    </Badge>
  );
}
