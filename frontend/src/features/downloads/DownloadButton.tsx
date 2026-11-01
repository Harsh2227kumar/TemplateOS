import { Download, Loader2 } from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { useDownloadGenerated, useDownloadVersion } from "@/hooks/queries";
import { ApiError } from "@/lib/api";

import { downloadErrorMessage, type DownloadFormat } from "./history-model";

interface DownloadButtonProps {
  documentId: number;
  format: DownloadFormat;
  /** A specific version; the latest when omitted. */
  version?: number | null;
  /** Draft name, for the file name when the header is not readable. */
  name?: string | null;
  label?: string;
  size?: ButtonProps["size"];
  variant?: ButtonProps["variant"];
  className?: string;
  /** Shown as the tooltip and disables the button. */
  disabledReason?: string | null;
}

/**
 * Download a generated file with the session cookies (V1.7 P3). The server
 * records the download; the history lists refresh after it. Errors are
 * explained by status (403 / 404 / 409 / 410).
 */
export function DownloadButton({
  documentId,
  format,
  version = null,
  name = null,
  label,
  size = "sm",
  variant = "outline",
  className,
  disabledReason = null,
}: DownloadButtonProps) {
  const latest = useDownloadGenerated();
  const versioned = useDownloadVersion();
  const busy = latest.isPending || versioned.isPending;
  const text = label ?? format.toUpperCase();

  const handleClick = async () => {
    try {
      if (version) await versioned.mutateAsync({ documentId, version, format, name });
      else await latest.mutateAsync({ documentId, format, name });
    } catch (err) {
      toast({
        variant: "destructive",
        title: `Couldn't download the ${format.toUpperCase()}`,
        description: downloadErrorMessage(err instanceof ApiError ? err.status : undefined, err instanceof Error ? err.message : undefined),
      });
    }
  };

  return (
    <Button
      type="button"
      size={size}
      variant={variant}
      className={className}
      disabled={busy || Boolean(disabledReason)}
      title={disabledReason ?? undefined}
      onClick={() => void handleClick()}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
      {text}
    </Button>
  );
}
