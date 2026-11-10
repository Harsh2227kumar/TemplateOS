import { AlertTriangle, Loader2, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MonoKey } from "@/components/fields/pipeline-ui";
import type { DetectionWarnings } from "@/lib/api";
import { KEY_PATTERN, KEY_RULE_MESSAGE } from "@/lib/template-pipeline";

import type { DetectionBusy } from "./types";

interface InvalidPlaceholdersCardProps {
  invalid: DetectionWarnings["invalid_names"];
  fixKeys: Record<string, string>;
  onFixKeyChange: (raw: string, key: string) => void;
  onFix: (raws: string[]) => void;
  /** Existing field keys, to say when a fix reuses one. */
  fieldNames: Set<string>;
  canManage: boolean;
  busy: DetectionBusy;
}

/** Placeholders whose names the document engine cannot read, with a rename-and-fix form. */
export function InvalidPlaceholdersCard({
  invalid,
  fixKeys,
  onFixKeyChange,
  onFix,
  fieldNames,
  canManage,
  busy,
}: InvalidPlaceholdersCardProps) {
  return (
    <Card className="border-red-200">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-base text-red-700">
              <AlertTriangle className="h-5 w-5" />
              Invalid placeholders ({invalid.length})
            </CardTitle>
            <CardDescription>
              These were skipped. Fix renames them in the cleaned copy and adds the fields.
            </CardDescription>
          </div>
          {canManage && invalid.length > 1 && (
            <Button
              size="sm"
              className="gap-1.5"
              disabled={!!busy || invalid.some((w) => !KEY_PATTERN.test(fixKeys[w.raw] ?? ""))}
              onClick={() => onFix(invalid.map((w) => w.raw))}
            >
              <Wrench className="h-4 w-4" />
              Fix all
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {invalid.map((warning) => {
          const key = fixKeys[warning.raw] ?? "";
          const valid = KEY_PATTERN.test(key);
          return (
            <div key={warning.raw} className="space-y-2 rounded-lg border border-red-100 bg-red-50/50 p-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <code className="break-all rounded bg-white px-1.5 py-0.5 font-mono text-xs text-red-700">
                  {`{{${warning.raw}}}`}
                </code>
                <span className="text-xs text-slate-500">
                  {warning.count} occurrence{warning.count === 1 ? "" : "s"}
                </span>
              </div>
              {canManage ? (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <Input
                      value={key}
                      aria-label={`New key for ${warning.raw}`}
                      aria-invalid={!valid}
                      className={`h-9 font-mono text-sm ${valid ? "" : "border-red-400"}`}
                      onChange={(e) => onFixKeyChange(warning.raw, e.target.value.trim())}
                    />
                    {!valid && <p className="mt-1 text-xs text-red-600">{KEY_RULE_MESSAGE}</p>}
                    {valid && fieldNames.has(key) && (
                      <p className="mt-1 text-xs text-slate-500">Uses the existing “{key}” field.</p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    className="h-9 gap-1.5"
                    disabled={!valid || !!busy}
                    onClick={() => onFix([warning.raw])}
                  >
                    {busy === "fix" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
                    Fix
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-slate-600">
                  Suggested name: <MonoKey name={warning.suggested_key} />
                </p>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
