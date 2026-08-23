import { useEffect, useState } from "react";
import { FileText, FolderOpen } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { templatesApi, TemplateListItem } from "@/lib/api";

export function DashboardPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const firstName = user?.full_name?.split(" ")[0] || "User";

  const [myTemplates, setMyTemplates] = useState<TemplateListItem[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);

  useEffect(() => {
    async function fetchTemplates() {
      if (!token) return;
      try {
        const data = await templatesApi.getMyTemplates(token);
        setMyTemplates(data);
      } catch (err) {
        // silent fail
      } finally {
        setTemplatesLoading(false);
      }
    }
    fetchTemplates();
  }, [token]);

  const getCategoryColor = (category: string) => {
    switch (category.toLowerCase()) {
      case "notice": return "bg-blue-100 text-blue-800";
      case "mom": return "bg-purple-100 text-purple-800";
      case "report": return "bg-green-100 text-green-800";
      case "application": return "bg-orange-100 text-orange-800";
      case "letter": return "bg-cyan-100 text-cyan-800";
      case "certificate": return "bg-yellow-100 text-yellow-800";
      case "proposal": return "bg-pink-100 text-pink-800";
      case "invoice": return "bg-slate-100 text-slate-800";
      case "custom": return "bg-gray-100 text-gray-800";
      default: return "bg-gray-100 text-gray-800";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "uploaded": return "bg-yellow-400";
      case "active": return "bg-green-400";
      case "field_configured": return "bg-blue-400";
      case "archived": return "bg-gray-400";
      default: return "bg-gray-400";
    }
  };

  const renderTemplatesContent = () => {
    if (templatesLoading) {
      return (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-16 bg-slate-100 rounded-lg animate-pulse" />
          ))}
        </div>
      );
    }
    
    if (myTemplates.length === 0) {
      return (
        <EmptyState
          icon={FolderOpen}
          title="No templates yet"
          description="Uploaded templates, statuses, and quick actions will live in this panel."
          actionLabel="Upload Template"
          onAction={() => navigate("/upload-template")}
        />
      );
    }

    const displayTemplates = myTemplates.slice(0, 5);

    return (
      <div className="flex flex-col h-full">
        <div className="space-y-2 flex-1">
          {displayTemplates.map(t => (
            <div 
              key={t.id}
              onClick={() => navigate(`/templates/${t.id}`)}
              className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors"
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <div 
                  className={`h-2 w-2 rounded-full shrink-0 ${getStatusColor(t.status)}`}
                  title={`Status: ${t.status}`}
                />
                <div className="min-w-0">
                  <p className="font-medium text-sm text-slate-900 truncate" title={t.name}>
                    {t.name}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(t.created_at))}
                  </p>
                </div>
              </div>
              <Badge variant="secondary" className={`ml-2 shrink-0 border-transparent ${getCategoryColor(t.category)}`}>
                {t.category.charAt(0).toUpperCase() + t.category.slice(1)}
              </Badge>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-slate-100">
          <Link to="/templates" className="text-sm font-medium text-slate-600 hover:text-slate-900">
            View All Templates &rarr;
          </Link>
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      {/* Welcome Hero */}
      <section className="relative overflow-hidden rounded-2xl bg-slate-900 px-6 py-10 sm:px-10 sm:py-12">
        <div className="relative z-10 text-white">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-400">Document Workspace</p>
          <h1 className="mt-3 text-3xl font-semibold sm:text-4xl">Welcome back, {firstName}</h1>
          <p className="mt-4 max-w-2xl text-base text-slate-300">
            Upload DOCX templates, configure fields, and generate polished documents with AI assistance. Start by uploading a template or browsing the library.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Button asChild className="bg-white text-slate-900 hover:bg-slate-100">
              <Link to="/upload-template">
                Upload Template
              </Link>
            </Button>
            <Button asChild variant="outline" className="border-slate-600 bg-slate-800/50 text-white hover:bg-slate-700">
              <Link to="/templates">
                Browse Templates
              </Link>
            </Button>
          </div>
        </div>
        {/* Decorative background element */}
        <div className="absolute right-0 top-0 -mr-20 -mt-20 h-64 w-64 rounded-full bg-slate-800 opacity-50 blur-3xl" aria-hidden="true" />
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Recent Documents */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Recent Documents</h2>
          </div>
          <EmptyState
            icon={FileText}
            title="No recent documents yet"
            description="Generated files and latest drafts will appear here once document flows are connected."
            actionLabel="Create Document"
          />
        </section>

        {/* My Templates */}
        <section className="flex flex-col">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">My Templates</h2>
          </div>
          <div className="flex-1 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            {renderTemplatesContent()}
          </div>
        </section>
      </div>
    </div>
  );
}
