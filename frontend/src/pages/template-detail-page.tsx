import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { templatesApi, TemplateResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Download, FilePlus2 } from "lucide-react";

export function TemplateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<TemplateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string; status?: number } | null>(null);

  useEffect(() => {
    fetchTemplate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchTemplate = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("templateos_access_token") || "";
      const data = await templatesApi.getTemplateDetail(token, Number(id));
      setTemplate(data);
    } catch (err: any) {
      setError({
        message: err.message || "Failed to load template",
        status: err.status,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const formattedDate = template ? new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(template.created_at)) : "";

  if (isLoading) {
    return (
      <div className="max-w-4xl space-y-8">
        <Skeleton className="h-10 w-32" />
        <div className="space-y-4">
          <Skeleton className="h-10 w-3/4" />
          <div className="flex gap-2">
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-20" />
          </div>
        </div>
        <Skeleton className="h-20 w-full" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl space-y-6 text-center py-20">
        <h2 className="text-2xl font-semibold">
          {error.status === 404 ? "Template not found" : 
           error.status === 403 ? "You do not have access to this template" : 
           "Something went wrong"}
        </h2>
        {error.status !== 404 && error.status !== 403 && (
          <p className="text-slate-600">{error.message}</p>
        )}
        <div className="flex justify-center gap-4 mt-6">
          <Button variant="outline" onClick={() => navigate("/templates")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Library
          </Button>
          {error.status !== 404 && error.status !== 403 && (
            <Button onClick={fetchTemplate}>Retry</Button>
          )}
        </div>
      </div>
    );
  }

  if (!template) return null;

  return (
    <div className="max-w-4xl space-y-8 pb-10">
      <Button variant="ghost" onClick={() => navigate("/templates")} className="-ml-4 text-slate-600">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Library
      </Button>

      <div>
        <h1 className="text-3xl font-semibold mb-4">{template.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline" className="bg-slate-50">
            Status: <span className="ml-1 capitalize">{template.status.replace("_", " ")}</span>
          </Badge>
          <Badge variant="outline" className="bg-slate-50">
            Category: <span className="ml-1 capitalize">{template.category}</span>
          </Badge>
          <Badge variant="outline" className="bg-slate-50">
            Visibility: <span className="ml-1 capitalize">{template.visibility}</span>
          </Badge>
        </div>
      </div>

      {template.description && (
        <div className="prose prose-slate max-w-none">
          <p className="text-slate-700 leading-relaxed">{template.description}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 bg-slate-50 p-6 rounded-xl border">
        <div className="space-y-4">
          <div>
            <div className="text-sm font-medium text-slate-500">Original Filename</div>
            <div className="mt-1 text-slate-900">{template.original_filename || "N/A"}</div>
          </div>
          <div>
            <div className="text-sm font-medium text-slate-500">File Size</div>
            <div className="mt-1 text-slate-900">
              {template.file_size_bytes ? formatBytes(template.file_size_bytes) : "Unknown"}
            </div>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <div className="text-sm font-medium text-slate-500">Uploaded On</div>
            <div className="mt-1 text-slate-900">{formattedDate}</div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm font-medium text-slate-500">Version</div>
              <div className="mt-1 text-slate-900">v{template.version}</div>
            </div>
            <div>
              <div className="text-sm font-medium text-slate-500">Template ID</div>
              <div className="mt-1 text-slate-900">{template.id}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 pt-4 border-t">
        <Button disabled title="Coming in V1.3" className="gap-2">
          <FilePlus2 className="h-4 w-4" />
          Use This Template
        </Button>
        <Button variant="outline" disabled title="Coming soon" className="gap-2">
          <Download className="h-4 w-4" />
          Download Original
        </Button>
      </div>
    </div>
  );
}
