import { Eraser, ScanSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface DetectPlaceholdersCardProps {
  canManage: boolean;
  hasProcessed: boolean;
  busy: boolean;
  onDetect: () => void;
  onClean: () => void;
}

/** First-run prompt shown before detection has ever run on the template. */
export function DetectPlaceholdersCard({ canManage, hasProcessed, busy, onDetect, onClean }: DetectPlaceholdersCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScanSearch className="h-5 w-5 text-slate-500" />
          Detect placeholders
        </CardTitle>
        <CardDescription>
          Scan the {hasProcessed ? "cleaned copy" : "document"} for{" "}
          <span className="font-mono text-xs">{"{{placeholder}}"}</span> tokens. Each valid one becomes a
          form field with a suggested label and type.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-3">
        {canManage ? (
          <>
            <Button className="gap-2" onClick={onDetect} disabled={busy}>
              <ScanSearch className="h-4 w-4" />
              Detect placeholders
            </Button>
            {!hasProcessed && (
              <Button variant="outline" className="gap-2" onClick={onClean}>
                <Eraser className="h-4 w-4" />
                Clean first
              </Button>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-600">Only template managers can run placeholder detection.</p>
        )}
      </CardContent>
    </Card>
  );
}
